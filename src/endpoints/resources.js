import express from "express"
import { n3FromJsonld, ttlFromJsonld, checkJsonld } from "../rdf.js"
import connect from "../mongo.js"
import _ from "lodash"
import createError from "http-errors"

const resourcesRouter = express.Router()

const apiBaseUrl = process.env.API_BASE_URL

// Add the db to req
resourcesRouter.use(connect)

resourcesRouter.post("/:resourceId", [
  checkJsonld,
  (req, res, next) => {
    console.log(`Received post to ${req.params.resourceId}`)

    const resource = req.body
    const resourceUri = resourceUriFor(req)
    const timestamp = new Date()

    const saveResource = resourceForSave(
      resource,
      req.params.resourceId,
      resourceUri,
      timestamp
    )

    // See https://www.mongodb.com/blog/post/building-with-patterns-the-document-versioning-pattern
    // Add primary copy.
    req.db
      .collection("resources")
      .insert(saveResource)
      .then(() => {
        // And a version copy.
        req.db
          .collection("resourceVersions")
          .insert(saveResource)
          .then(() => {
            // Stub out resource metadata.
            const resourceMetadata = {
              id: req.params.resourceId,
              versions: [versionEntry(saveResource)],
            }
            req.db
              .collection("resourceMetadata")
              .insert(resourceMetadata)
              .then(() =>
                res.location(resourceUri).status(201).send(forReturn(resource))
              )
              .catch(next)
          })
          .catch(next)
      })
      .catch(next)
  },
])

resourcesRouter.put("/:resourceId", [
  checkJsonld,
  (req, res, next) => {
    console.log(`Received put to ${req.params.resourceId}`)

    const resource = req.body
    const timestamp = new Date()
    const resourceUri = resourceUriFor(req)
    const saveResource = resourceForSave(
      resource,
      req.params.resourceId,
      resourceUri,
      timestamp
    )

    // Replace primary copy.
    req.db
      .collection("resources")
      .update({ id: req.params.resourceId }, saveResource, {
        replaceOne: true,
      })
      .then((result) => {
        if (result.nModified !== 1) throw new createError.NotFound()

        // And a version copy.
        req.db
          .collection("resourceVersions")
          .insert(saveResource)
          .then(() => {
            // Apppend to resource metadata.
            req.db
              .collection("resourceMetadata")
              .update(
                { id: req.params.resourceId },
                { $push: { versions: versionEntry(saveResource) } }
              )
              .then(() => {
                res.send(forReturn(resource))
              })
              .catch(next)
          })
          .catch(next)
      })
      .catch(next)
  },
])

resourcesRouter.delete("/:resourceId", (req, res, next) => {
  console.log(`Received delete to ${req.params.resourceId}`)

  // Remove primary copy.
  req.db
    .collection("resources")
    .remove({ id: req.params.resourceId })
    .then((result) => {
      if (result.deletedCount !== 1) throw new createError.NotFound()

      // Remove version copies.
      req.db
        .collection("resourceVersions")
        .remove({ id: req.params.resourceId })
        .then(() => {
          // Remove resource metadata.
          req.db
            .collection("resourceMetadata")
            .remove({ id: req.params.resourceId })
            .then(() => {
              res.sendStatus(204)
            })
            .catch(next)
        })
        .catch(next)
    })
    .catch(next)
})

resourcesRouter.get("/:resourceId/versions", (req, res, next) => {
  req.db
    .collection("resourceMetadata")
    .findOne({ id: req.params.resourceId })
    .then((resourceMetadata) => {
      if (!resourceMetadata) return res.sendStatus(404)
      return res.send(forReturn(resourceMetadata))
    })
    .catch(next)
})

resourcesRouter.get("/:resourceId/version/:timestamp", (req, res, next) => {
  req.db
    .collection("resourceVersions")
    .findOne({ id: req.params.resourceId, timestamp: req.params.timestamp })
    .then((resource) => {
      if (!resource) return res.sendStatus(404)
      return res.send(forReturn(resource))
    })
    .catch(next)
})

resourcesRouter.get("/:resourceId", (req, res, next) => {
  req.db
    .collection("resources")
    .findOne({ id: req.params.resourceId })
    .then((resource) => {
      if (!resource) return res.sendStatus(404)
      const returnResource = forReturn(resource)
      res.format({
        "text/plain": () => res.send(JSON.stringify(returnResource, null, 2)),
        "text/html": () =>
          res.send(`<pre>${JSON.stringify(returnResource, null, 2)}</pre>`),
        "application/json": () => res.send(returnResource),
        "application/ld+json": () => res.send(returnResource.data),
        "text/n3": () =>
          n3FromJsonld(returnResource.data).then((n3) => res.send(n3)),
        "text/turtle": () =>
          ttlFromJsonld(returnResource.data).then((ttl) => res.send(ttl)),
        default: () => res.sendStatus(406),
      })
    })
    .catch(next)
})

/* eslint-disable prefer-destructuring */
resourcesRouter.get("/", (req, res, next) => {
  const data = []
  const limit = Number(req.query.limit) || 25
  const start = Number(req.query.start) || 1
  const query = queryFor(req.query)

  // Ask for one more so that can see if there is a next page.
  let nextPage = false
  req.db
    .collection("resources")
    .find(query, { skip: start - 1, limit: limit + 1 })
    .each((resource) => {
      if (data.length < limit) {
        data.push(forReturn(resource))
      } else {
        nextPage = true
      }
    })
    .then(() => {
      const links = {
        first: pageUrlFor(req, 0, limit, req.query),
      }
      if (start !== 1)
        links.prev = pageUrlFor(
          req,
          limit,
          Math.max(start - limit, 0),
          req.query
        )
      if (nextPage)
        links.next = pageUrlFor(req, limit, start + limit, req.query)
      res.send({ data, links })
    })
    .catch(next)
})

const resourceUriFor = (req) => {
  return `${baseUrlFor(req)}/${req.params.resourceId}`
}

const baseUrlFor = (req) => {
  if (apiBaseUrl) return `${apiBaseUrl}/resource`
  return `${req.protocol}://${req.hostname}:${req.port}/resource`
}

const pageUrlFor = (req, limit, start, qs) => {
  const params = { limit, start }
  Object.keys(qs).forEach((key) => {
    if (["group", "updatedAfter", "updatedBefore", "type"].includes(key)) {
      params[key] = qs[key]
    }
  })
  const queryString = Object.entries(params)
    .map(([key, value]) => [key, encodeURIComponent(value)].join("="))
    .join("&")
  return `${baseUrlFor(req)}?${queryString}`
}

const queryFor = (qs) => {
  const query = {}
  if (qs.group) query.group = qs.group
  if (qs.type) query.types = qs.type
  if (qs.updatedAfter || qs.updatedBefore) query.timestamp = {}
  if (qs.updatedAfter) query.timestamp.$gte = parseDate(qs.updatedAfter)
  if (qs.updatedBefore) query.timestamp.$lte = parseDate(qs.updatedBefore)
  return query
}

const parseDate = (dateString) => {
  const date = new Date(dateString)
  if (isNaN(date))
    throw new createError.BadRequest(`Invalid date-time: ${dateString}`)

  return date
}

const forReturn = (item) => {
  // Map ! back to . in key names
  const newItem = replaceInKeys(item, "!", ".")
  delete newItem._id
  return newItem
}

const resourceForSave = (resource, id, uri, timestamp) => {
  // Map . to ! in key names because Mongo doesn't like . in key names. Sigh.
  const newResource = replaceInKeys(resource, ".", "!")

  newResource.id = id
  // If resource has a uri, keep it. This is to support migrations.
  if (!newResource.uri) newResource.uri = uri
  newResource.timestamp = timestamp
  return newResource
}

const versionEntry = (resource) => ({
  timestamp: resource.timestamp,
  user: resource.user,
  group: resource.group,
  editGroups: resource.editGroups,
  templateId: resource.templateId,
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
