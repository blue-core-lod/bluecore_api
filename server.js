import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import { ttlFromJsonld, n3FromJsonld } from './utilities/rdf.js'
import jwt from 'express-jwt'
import jwksRsa from 'jwks-rsa'
import { connect } from './utilities/mongo.js'
import _ from 'lodash'

const app = express()

const cognitoUserPoolId = process.env.COGNITO_USER_POOL_ID || 'us-west-2_CGd9Wq136'
const awsRegion = process.env.AWS_REGION || 'us-west-2'
const apiBaseUrl = process.env.API_BASE_URL
// This allows turning off authentication, e.g., during migration.
const noAuth = process.env.NO_AUTH === 'true'
const port = process.env.PORT || 3000

// Configure mongo and start server.
let db
connect()
  .then((newDb) => {
    db = newDb
    app.listen(port, () => {
      console.log(`listening on ${port}`)
    })
  })
  .catch((error) => console.error(error))

// Increase the allowed payload size.
app.use(express.json({limit: '1mb'}))

// CORS should probably be tightened down.
app.use(cors({exposedHeaders: 'Location'}))
app.options('*', cors())
app.use(helmet())

// JWT
const publicKeySecret = jwksRsa.expressJwtSecret({
    cache: true,
    rateLimit: true,
    jwksUri: `https://cognito-idp.${awsRegion}.amazonaws.com/${cognitoUserPoolId}/.well-known/jwks.json`
  })

app.use(jwt({ secret: publicKeySecret, algorithms: ['RS256'] }).unless({
  method: ['GET'],
  custom: () => noAuth,
}))

// In general, trying to follow https://jsonapi.org/

// This regex path will match legacy uris like http://localhost:3000/repository/pcc/3a941f1e-025f-4a6f-80f1-7f23203186a2
app.post('/repository/:resourceId([^/]+/?[^/]+?)', (req, res) => {
  console.log(`Received post to ${req.params.resourceId}`)

  const resource = req.body
  const resourceUri = resourceUriFor(req.protocol, req.hostname, port, req.params.resourceId)
  const timestamp = new Date().toISOString()

  const saveResource = resourceForSave(resource, req.params.resourceId, resourceUri, timestamp)

  // See https://www.mongodb.com/blog/post/building-with-patterns-the-document-versioning-pattern
  // Add primary copy.
  db.collection('resources').insertOne(saveResource)
    .then(() => {
      // And a version copy.
      db.collection('resourceVersions').insertOne(saveResource)
        .then(() => {
          // Stub out resource metadata.
          const resourceMetadata = {id: req.params.resourceId, versions: [versionEntry(saveResource)]}
          db.collection('resourceMetadata').insertOne(resourceMetadata)
            .then(() => res.location(resourceUri).status(201).send(forReturn(resource)))
            .catch(handleError(res))
        })
        .catch(handleError(res, req.params.resourceId))
    })
    .catch(handleError(res, req.params.resourceId))
})

// This regex path will match legacy uris like http://localhost:3000/repository/pcc/3a941f1e-025f-4a6f-80f1-7f23203186a2
app.put('/repository/:resourceId([^/]+/?[^/]+?)', (req, res) => {
  console.log(`Received put to ${req.params.resourceId}`)

  const resource = req.body
  const timestamp = new Date().toISOString()
  const resourceUri = resourceUriFor(req.protocol, req.hostname, port, req.params.resourceId)
  const saveResource = resourceForSave(resource, req.params.resourceId, resourceUri, timestamp)

  // Replace primary copy.
  db.collection('resources').replaceOne({id: req.params.resourceId}, saveResource)
    .then((result) => {
      if(result.matchedCount !== 1) return res.sendStatus(404)

      // And a version copy.
      db.collection('resourceVersions').insertOne(saveResource)
        .then(() => {
          // Apppend to resource metadata.
          db.collection('resourceMetadata').updateOne({id: req.params.resourceId}, { $push: { versions: versionEntry(saveResource)}})
            .then(() => {
              res.send(forReturn(resource))
            })
            .catch(handleError(res, req.params.resourceId))
        })
        .catch(handleError(res, req.params.resourceId))
    })
    .catch(handleError(res, req.params.resourceId))
})

app.get('/repository/:resourceId/versions', (req, res) => {
  db.collection('resourceMetadata').findOne({id: req.params.resourceId})
    .then((resourceMetadata) => {
      if(!resourceMetadata) return res.sendStatus(404)
      return res.send(forReturn(resourceMetadata))
    })
    .catch(handleError(res, req.params.resourceId))
})

app.get('/repository/:resourceId/version/:timestamp', (req, res) => {
  db.collection('resourceVersions').findOne({id: req.params.resourceId, timestamp: req.params.timestamp})
    .then((resource) => {
      if(!resource) return res.sendStatus(404)
      return res.send(forReturn(resource))
    })
    .catch(handleError(res, req.params.resourceId))
})

// This regex path will match legacy uris like http://localhost:3000/repository/pcc/3a941f1e-025f-4a6f-80f1-7f23203186a2
app.get('/repository/:resourceId([^/]+/?[^/]+?)', (req, res) => {
  db.collection('resources').findOne({id: req.params.resourceId})
    .then((resource) => {
      if(!resource) return res.sendStatus(404)
      const returnResource = forReturn(resource)
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
    .catch(handleError(res, req.params.resourceId))
})

app.get('/', (req, res) => {
  res.send({all: "good"})
})

const handleError = (res, id) => {
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
    console.error(`Error for ${id}`, err)
    res.status(statusCode).send(errors)
  }
}

const resourceUriFor = (protocol, hostname, port, resourceId) => {
  if(apiBaseUrl) return `${apiBaseUrl}/repository/${resourceId}`
  return `${protocol}://${hostname}:${port}/repository/${resourceId}`
}

const forReturn = (item) => {
  // Map ! back to . in key names
  const newItem = replaceInKeys(item, '!', '.')
  delete newItem._id
  return newItem
}

const resourceForSave = (resource, id, uri, timestamp) => {
  // Map . to ! in key names because Mongo doesn't like . in key names. Sigh.
  const newResource = replaceInKeys(resource, '.', '!')

  newResource.id = id
  // If resource has a uri, keep it. This is to support migrations.
  if(!newResource.uri) newResource.uri = uri
  newResource.timestamp = timestamp
  return newResource
}

const versionEntry = (resource) => ({
  timestamp: resource.timestamp,
  user: resource.user,
  group: resource.group,
  templateId: resource.templateId
})

const replaceInKeys = (obj, from, to) => {
  return _.cloneDeepWith(obj, function (cloneObj) {
    if (!_.isPlainObject(cloneObj)) return
    const newObj = {}
    _.keys(cloneObj).forEach((key) => {
      const newKey = key.replace(new RegExp(`\\${from}`, "g"), to)
      newObj[newKey] = replaceInKeys(cloneObj[key], from, to)
    })
    return newObj
  })
}
