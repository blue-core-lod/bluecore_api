import express from 'express'
import { ttlFromJsonld, n3FromJsonld } from '../rdf.js'
import _ from 'lodash'
import { handleError } from '../error.js'

const resourcesRouter = express.Router()

const apiBaseUrl = process.env.API_BASE_URL

resourcesRouter.post('/:resourceId', (req, res) => {
  console.log(`Received post to ${req.params.resourceId}`)

  const resource = req.body
  const resourceUri = resourceUriFor(req.protocol, req.hostname, req.port, req.params.resourceId)
  const saveResource = resourceForSave(resource, req.params.resourceId, resourceUri)

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
            .then(() => res.location(resourceUri).status(201).send(forReturn(saveResource)))
            .catch(handleError(req, res))
        })
        .catch(handleError(req, res))
    })
    .catch(handleError(req, res))
})

resourcesRouter.put('/:resourceId', (req, res) => {
  console.log(`Received put to ${req.params.resourceId}`)

  const resource = req.body
  const resourceUri = resourceUriFor(req.protocol, req.hostname, req.port, req.params.resourceId)
  const saveResource = resourceForSave(resource, req.params.resourceId, resourceUri)

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
              res.send(forReturn(saveResource))
            })
            .catch(handleError(req, res))
        })
        .catch(handleError(req, res))
    })
    .catch(handleError(req, res))
})

resourcesRouter.get('/:resourceId/versions', (req, res) => {
  req.db.collection('resourceMetadata').findOne({id: req.params.resourceId})
    .then((resourceMetadata) => {
      if(!resourceMetadata) return res.sendStatus(404)
      return res.send(forReturn(resourceMetadata))
    })
    .catch(handleError(req, res))
})

resourcesRouter.get('/:resourceId/version/:timestamp', (req, res) => {
  req.db.collection('resourceVersions').findOne({id: req.params.resourceId, timestamp: new Date(req.params.timestamp)})
    .then((resource) => {
      if(!resource) return res.sendStatus(404)
      return res.send(forReturn(resource))
    })
    .catch(handleError(req, res))
})

resourcesRouter.get('/:resourceId', (req, res) => {
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
    .catch(handleError(req, res))
})

const resourceUriFor = (protocol, hostname, port, resourceId) => {
  if(apiBaseUrl) return `${apiBaseUrl}/resource/${resourceId}`
  return `${protocol}://${hostname}:${port}/resource/${resourceId}`
}

const forReturn = (item) => {
  // Map ! back to . in key names
  const newItem = replaceInKeys(item, '!', '.')
  delete newItem._id
  return newItem
}

const resourceForSave = (resource, id, uri) => {
  // Map . to ! in key names because Mongo doesn't like . in key names. Sigh.
  const newResource = replaceInKeys(resource, '.', '!')

  newResource.id = id
  // If resource has a uri, keep it. This is to support migrations.
  if(!newResource.uri) newResource.uri = uri
  // For querying, need to use a JS date
  // Use provided timestamp or create a new one.
  // Allowing a provided timestamp can be removed once migration is completed.
  const timestamp = newResource.timestamp ? new Date(newResource.timestamp) : new Date()
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
