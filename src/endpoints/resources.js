import express from "express"
import { n3FromJsonld, ttlFromJsonld, checkJsonld } from "../rdf.js"
import connect from "../mongo.js"
import createError from "http-errors"
import { canDelete, canCreate, canEdit } from "../permissions.js"
import {
  resourceUriFor,
  pageUrlFor,
  queryFor,
  parseDate,
  forReturn,
  resourceForSave,
  versionEntry,
  mergeRefs,
} from "./resourcesHelpers.js"

const resourcesRouter = express.Router()

// Add the db to req
resourcesRouter.use(connect)

resourcesRouter.post("/:resourceId", [
  checkJsonld,
  canCreate,
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
                res
                  .location(resourceUri)
                  .status(201)
                  .send(forReturn(resource, req.db))
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
  canEdit,
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
                res.send(forReturn(resource, req.db))
              })
              .catch(next)
          })
          .catch(next)
      })
      .catch(next)
  },
])

resourcesRouter.delete("/:resourceId", [
  canDelete,
  (req, res, next) => {
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
  },
])

resourcesRouter.get("/:resourceId/relationships", (req, res, next) => {
  const projection = {
    id: 1,
    bfAdminMetadataRefs: 1,
    bfItemRefs: 1,
    bfInstanceRefs: 1,
    bfWorkRefs: 1,
    uri: 1,
    types: 1,
  }
  return req.db
    .collection("resources")
    .findOne({ id: req.params.resourceId }, { projection })
    .then((resource) => {
      if (!resource) return res.sendStatus(404)
      const query = {
        $or: [
          { bfAdminMetadataRefs: resource.uri },
          { bfItemRefs: resource.uri },
          { bfInstanceRefs: resource.uri },
          { bfWorkRefs: resource.uri },
        ],
      }
      delete resource.uri
      delete resource.types
      delete resource._id
      return req.db
        .collection("resources")
        .find(query, { projection })
        .then((resourceRefs) => {
          return res.send(mergeRefs(resource, resourceRefs))
        })
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
    .findOne({
      id: req.params.resourceId,
      timestamp: parseDate(req.params.timestamp),
    })
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

export default resourcesRouter
