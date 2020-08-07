import express from 'express'
import { v4 as uuidv4 } from 'uuid'
import MongoClient  from 'mongodb'
import cors from 'cors'
import helmet from 'helmet'
import { ttlFromJsonld, n3FromJsonld } from './utilities/rdf.js'
import jwt from 'express-jwt'
import jwksRsa from 'jwks-rsa'

const app = express()

const port = process.env.PORT || 3000
const dbUsername = process.env.MONGODB_USERNAME || 'sinopia'
const dbPassword = process.env.MONGODB_PASSWORD || 'sekret'
const dbName = process.env.MONGODB_DB || 'sinopia_repository'
const dbHost = process.env.MONGODB_HOST || 'localhost'
const dbPort = process.env.MONGODB_PORT || '27017'

const cognitoUserPoolId = process.env.COGNITO_USER_POOL_ID || 'us-west-2_CGd9Wq136'
const awsRegion = process.env.AWS_REGION || 'us-west-2'

let db
// Configure mongo and start server.
MongoClient.connect(`mongodb://${dbUsername}:${dbPassword}@${dbHost}:${dbPort}/${dbName}`, { useUnifiedTopology: true })
  .then((client) => {
    db = client.db(dbName)
    app.listen(port, () => {
      console.log(`listening on ${port}`)
    })
  })
  .catch((error) => console.error(error))

app.use(express.json())

// CORS should probably be tightened down.
app.use(cors({exposedHeaders: 'Location'}))
app.options('*', cors())
app.use(helmet())

const publicKeySecret = jwksRsa.expressJwtSecret({
    cache: true,
    rateLimit: true,
    jwksUri: `https://cognito-idp.${awsRegion}.amazonaws.com/${cognitoUserPoolId}/.well-known/jwks.json`
  })

// In general, trying to follow https://jsonapi.org/

app.post('/repository', jwt({ secret: publicKeySecret, algorithms: ['RS256'] }), (req, res) => {
  const resource = req.body

  // Using the template id for a template, otherwise a uuid.
  const resourceId = isTemplate(resource.data) ? templateIdFor(resource.data) : uuidv4()
  const resourceUri = resourceUriFor(req.hostname, port, resourceId)
  const timestamp = new Date().toISOString()

  const saveResource = resourceForSave(resource, resourceId, timestamp)

  // See https://www.mongodb.com/blog/post/building-with-patterns-the-document-versioning-pattern
  // Add primary copy.
  // TBD: checkKeys allows saving documents with periods in keys. Is this a problem for querying / updating?
  db.collection('resources').insertOne(saveResource, {checkKeys: false})
    .then(() => {
      // And a version copy.
      db.collection('resourceVersions').insertOne(saveResource, {checkKeys: false})
        .then(() => {
          // Stub out resource metadata.
          const resourceMetadata = {id: resourceId, versions: [{timestamp: timestamp, user: resource.user, group: resource.group}]}
          db.collection('resourceMetadata').insertOne(resourceMetadata)
            .then(() => res.location(resourceUri).status(201).send(resourceForReturn(resource, resourceUri)))
            .catch(handleError(res))
        })
        .catch(handleError(res))
    })
    .catch(handleError(res))
})

app.put('/repository/:resourceId', jwt({ secret: publicKeySecret, algorithms: ['RS256'] }), (req, res) => {
  const resource = req.body
  const timestamp = new Date().toISOString()
  const resourceUri = resourceUriFor(req.hostname, port, req.params.resourceId)
  const saveResource = resourceForSave(resource, req.params.resourceId, timestamp)

  // Replace primary copy.
  db.collection('resources').replaceOne({id: req.params.resourceId}, saveResource, {checkKeys: false})
    .then((result) => {
      if(result.matchedCount !== 1) return res.sendStatus(404)

      // And a version copy.
      db.collection('resourceVersions').insertOne(saveResource, {checkKeys: false})
        .then(() => {
          // Apppend to resource metadata.
          db.collection('resourceMetadata').updateOne({id: req.params.resourceId}, { $push: { versions: {timestamp: timestamp, user: resource.user, group: resource.group}}})
            .then(() => {
              res.send(resourceForReturn(resource, resourceUri))
            })
            .catch(res, handleError)
        })
        .catch(res, handleError)
    })
    .catch(res, handleError)
})

app.get('/repository/:resourceId/versions', (req, res) => {
  db.collection('resourceMetadata').findOne({id: req.params.resourceId})
    .then((resourceMetadata) => {
      if(!resourceMetadata) return res.sendStatus(404)
      return res.send(forReturn(resourceMetadata, resourceUri))
    })
    .catch(res, handleError)
})

app.get('/repository/:resourceId/version/:timestamp', (req, res) => {
  db.collection('resourceVersions').findOne({id: req.params.resourceId, timestamp: req.params.timestamp})
    .then((resource) => {
      if(!resource) return res.sendStatus(404)
      const resourceUri = resourceUriFor(req.hostname, port, req.params.resourceId)
      return res.send(resourceForReturn(resource, resourceUri))
    })
    .catch(res, handleError)
})

app.get('/repository/:resourceId', (req, res) => {
  db.collection('resources').findOne({id: req.params.resourceId})
    .then((resource) => {
      if(!resource) return res.sendStatus(404)
      const resourceUri = resourceUriFor(req.hostname, port, req.params.resourceId)
      const returnResource = resourceForReturn(resource, resourceUri)
      res.format({
        'text/plain': () => res.send(JSON.stringify(returnResource, null, 2)),
        'text/html': () => res.send(`<pre>${JSON.stringify(returnResource, null, 2)}</pre>`),
        'application/json': () => res.send(returnResource),
        'application/ld+json': () => res.send(returnResource.data),
        'text/n3': () => n3FromJsonld(returnResource.data)
          .then((n3) => res.send(n3)),
        'text/turtle': () => ttlFromJsonld(returnResource.data)
          .then((ttl) => res.send(ttl)),
        default: () => res.sendStatus(406)
      })
    })
    .catch(handleError(res))
})

const handleError = (res) => {
  return (err) => {
    const errors = []
    let statusCode = 500
    // Mongo error for dupe key
    if(err.code === 11000) {
      // Conflict
      errors.push({title: 'Resource id is not unique', details: err.toString(), code: '409'})
      statusCode = 409
    } else {
      errors.push({title: 'Server error', details: err.toString(), code: '500'})
    }
    console.error(err)
    res.status(statusCode).send(errors)
  }
}

const resourceUriFor = (hostname, port, resourceId) => `http://${hostname}:${port}/repository/${resourceId}`

const resourceForReturn = (resource, uri) => {
  const newResource = {...resource}
  delete newResource._id
  newResource.uri = uri
  return newResource
}

const forReturn = (item) => {
  const newItem = {...item}
  delete newItem._id
  return newItem
}

const resourceForSave = (resource, id, timestamp) => {
  const newResource = {...resource}
  newResource.id = id
  newResource.timestamp = timestamp
  delete newResource.uri
  return newResource
}

const isTemplate = (data) => {
  // Looking for:
  // { '@id': '', '@type': 'http://sinopia.io/vocabulary/ResourceTemplate' }
  return data.some((triple) => triple['@id'] === '' && triple['@type'] === 'http://sinopia.io/vocabulary/ResourceTemplate')
}

const templateIdFor = (data) => {
  // Looking for:
  // { '@id': '', 'http://sinopia.io/vocabulary/hasResourceId': { '@id': 'resourceTemplate:bf2:Title' }}
  const resourceIdTriple = data.find((triple) => triple['@id'] === '' && triple['http://sinopia.io/vocabulary/hasResourceId'])
  return resourceIdTriple['http://sinopia.io/vocabulary/hasResourceId']['@id']
}
