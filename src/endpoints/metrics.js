import express from "express"
import connect from "../mongo.js"

const metricsRouter = express.Router()

// Add the db to req
metricsRouter.use(connect)

/**
 * Returns the mongo query to use for the specified resource type
 * @param {string} resourceType  The resource type ("template", "resource" or "all")
 * @returns {object} The query to send to mongo to filter by the requested type
 */
const getResourceQuery = (resourceType) => {
  if (resourceType === "template") {
    return { types: "http://sinopia.io/vocabulary/ResourceTemplate" }
  }
  if (resourceType === "resource") {
    return {
      types: {
        $not: { $eq: "http://sinopia.io/vocabulary/ResourceTemplate" },
      },
    }
  }
  // This is reached by sending "all" (we cannot get any other values since resourceType is an enum contrained by openapi)
  return { types: { $regex: ".*" } }
}

metricsRouter.get("/userCount", (req, res, next) => {
  req.db
    .collection("users")
    .count()
    .then((response) => res.send({ count: response }))
    .catch(next)
})

metricsRouter.get("/resourceCount/:resourceType", (req, res, next) => {
  req.db
    .collection("resources")
    .count(getResourceQuery(req.params.resourceType))
    .then((response) => res.send({ count: response }))
    .catch(next)
})

metricsRouter.get("/createdCount/:resourceType", (req, res, next) => {
  const query = [
    {
      $match: getResourceQuery(req.params.resourceType),
    },
    {
      $lookup: {
        from: "resourceMetadata",
        localField: "id",
        foreignField: "id",
        as: "resourceMetadata",
      },
    },
    { $unwind: "$resourceMetadata" },
    {
      $match: {
        "resourceMetadata.versions.0.timestamp": {
          $gt: new Date(req.query.startDate),
          $lt: new Date(req.query.endDate),
        },
      },
    },
    { $count: "count" },
  ]

  // Add the group filter to the query if present in the request
  if (req.query.group) {
    query[0].$match.group = req.query.group
  }

  req.db
    .collection("resources")
    .aggregate(query)
    .then((response) => res.send(forAggregateReturn(response)))
    .catch(next)
})

metricsRouter.get("/editedCount/:resourceType", (req, res, next) => {
  const query = [
    {
      $match: getResourceQuery(req.params.resourceType),
    },
    {
      $lookup: {
        from: "resourceMetadata",
        localField: "id",
        foreignField: "id",
        as: "resourceMetadata",
      },
    },
    { $unwind: "$resourceMetadata" },
    {
      $match: {
        "resourceMetadata.versions.timestamp": {
          $gt: new Date(req.query.startDate),
          $lt: new Date(req.query.endDate),
        },
      },
    },
    { $group: { _id: "$id" } },
    { $count: "count" },
  ]

  // Add the group filter to the query if present in the request
  if (req.query.group) {
    query[0].$match.group = req.query.group
  }

  req.db
    .collection("resources")
    .aggregate(query)
    .then((response) => res.send(forAggregateReturn(response)))
    .catch(next)
})

/**
 * Returns the response to the client for count aggregate mongo queries
 * Aggregate count queries return an array, and we are returning the count from this, so return the first element.
 * But if the query count is 0, the response is an empty array, so we want to return a 0 count instead in this case.
 * @param {string} response  Response from the mongo query
 * @returns {object} The object response to return to the user
 */
const forAggregateReturn = (response) => {
  if (response.length === 0) {
    return { count: 0 }
  }
  return response[0]
}

export default metricsRouter
