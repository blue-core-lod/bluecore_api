import express from 'express'
import { ttlFromJsonld, n3FromJsonld } from '../rdf.js'
import _ from 'lodash'

const resourcesRouter = express.Router()

const apiBaseUrl = process.env.API_BASE_URL

// This regex path will match legacy uris like http://localhost:3000/repository/pcc/3a941f1e-025f-4a6f-80f1-7f23203186a2
resourcesRouter.post('/:resourceId([^/]+/?[^/]+?)', (req, res) => {
  console.log(`Received post to ${req.params.resourceId}`)

  const resource = req.body
  const resourceUri = resourceUriFor(req)
  const timestamp = new Date().toISOString()

  const saveResource = resourceForSave(resource, req.params.resourceId, resourceUri, timestamp)

  // See https://www.mongodb.com/blog/post/building-with-patterns-the-document-versioning-pattern
  // Add primary copy.
  req.db.collection('resources').insert(saveResource)
    .then(() => {
      // And a version copy.
      req.db.collection('resourceVersions').insert(saveResource)
        .then(() => {
          // Stub out resource metadata.
          const resourceMetadata = {id: req.params.resourceId, versions: [versionEntry(saveResource)]}
          req.db.collection('resourceMetadata').insert(resourceMetadata)
            .then(() => res.location(resourceUri).status(201).send(forReturn(resource)))
            .catch(handleError(res))
        })
        .catch(handleError(res, req.params.resourceId))
    })
    .catch(handleError(res, req.params.resourceId))
})

// This regex path will match legacy uris like http://localhost:3000/repository/pcc/3a941f1e-025f-4a6f-80f1-7f23203186a2
resourcesRouter.put('/:resourceId([^/]+/?[^/]+?)', (req, res) => {
  console.log(`Received put to ${req.params.resourceId}`)

  const resource = req.body
  const timestamp = new Date().toISOString()
  const resourceUri = resourceUriFor(req)
  const saveResource = resourceForSave(resource, req.params.resourceId, resourceUri, timestamp)

  // Replace primary copy.
  req.db.collection('resources').update({id: req.params.resourceId}, saveResource, {replaceOne: true})
    .then((result) => {
      if(result.nModified !== 1) return res.sendStatus(404)

      // And a version copy.
      req.db.collection('resourceVersions').insert(saveResource)
        .then(() => {
          // Apppend to resource metadata.
          req.db.collection('resourceMetadata').update({id: req.params.resourceId}, { $push: { versions: versionEntry(saveResource)}})
            .then(() => {
              res.send(forReturn(resource))
            })
            .catch(handleError(res, req.params.resourceId))
        })
        .catch(handleError(res, req.params.resourceId))
    })
    .catch(handleError(res, req.params.resourceId))
})

resourcesRouter.get('/:resourceId/versions', (req, res) => {
  req.db.collection('resourceMetadata').findOne({id: req.params.resourceId})
    .then((resourceMetadata) => {
      if(!resourceMetadata) return res.sendStatus(404)
      return res.send(forReturn(resourceMetadata))
    })
    .catch(handleError(res, req.params.resourceId))
})

resourcesRouter.get('/:resourceId/version/:timestamp', (req, res) => {
  req.db.collection('resourceVersions').findOne({id: req.params.resourceId, timestamp: req.params.timestamp})
    .then((resource) => {
      if(!resource) return res.sendStatus(404)
      return res.send(forReturn(resource))
    })
    .catch(handleError(res, req.params.resourceId))
})

// This regex path will match legacy uris like http://localhost:3000/repository/pcc/3a941f1e-025f-4a6f-80f1-7f23203186a2
resourcesRouter.get('/:resourceId([^/]+/?[^/]+?)', (req, res) => {
  req.db.collection('resources').findOne({id: req.params.resourceId})
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

/* eslint-disable prefer-destructuring */
resourcesRouter.get('/', (req, res) => {
  const data = []
  const limit = Number(req.query.limit) || 25
  const start = Number(req.query.start) || 1
  const query = {}
  const group = req.query.group
  if(group) query.group = group
  // Ask for one more so that can see if there is a next page.
  let nextPage = false
  req.db.collection('resources').find(query, {skip: start - 1, limit: limit + 1}).each((resource) => {
    if(data.length < limit) {
      data.push(forReturn(resource))
    } else {
      nextPage = true
    }
  })
    .then(() => {
      const links = {
        first: pageUrlFor(req, 0, limit, group)
      }
      if(start !== 1) links.prev = pageUrlFor(req, limit, Math.max(start - limit, 0), group)
      if(nextPage) links.next = pageUrlFor(req, limit, start + limit, group)
      res.send({ data, links })
    })
})
/* eslint-enable prefer-destructuring */

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

const resourceUriFor = (req) => {
  return `${baseUrlFor(req)}/${req.params.resourceId}`
}

const baseUrlFor = (req) => {
  if(apiBaseUrl) return `${apiBaseUrl}/repository`
  return `${req.protocol}://${req.hostname}:${req.port}/repository`
}

const pageUrlFor = (req, limit, start, group) => {
  const params = { limit, start }
  if(group) params.group = group
  const queryString = Object.entries(params).map((param) => param.join('=')).join('&')
  return `${baseUrlFor(req)}?${queryString}`

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

export default resourcesRouter
