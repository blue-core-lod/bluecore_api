import express from "express"
import connect from "../mongo.js"

const metricsRouter = express.Router()

// Add the db to req
metricsRouter.use(connect)

// NOTE:
// When filtering for created resources by time, we want to only look at the very first timestamp in the versions element in
//  `resourceMetadata`. This is what `0` does in `resourceMetadata.versions.0.timestamp`
//  (only filter on the first timestamp in that array).
//  When filtering for edited resources, we want to look at all timestamps in that array.

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

/**
 * Returns the mongo query to use for the specified date range
 * @param {string} startDate The start date
 * @param {string} endDate The end date
 * @returns {object} The query to send to mongo to filter by the specified dates
 */
const getDateQuery = (startDate, endDate) => {
  return {
    $gte: new Date(startDate),
    $lte: new Date(endDate),
  }
}

metricsRouter.get("/userCount", (req, res, next) => {
  req.db
    .collection("users")
    .count()
    .then((response) => res.send({ count: response }))
    .catch(next)
})

metricsRouter.get("/resourceUserCount/:resourceType", (req, res, next) => {
  const query = getResourceQuery(req.params.resourceType)
  query.timestamp = getDateQuery(req.query.startDate, req.query.endDate)
  req.db
    .collection("resources")
    .distinct("user", query)
    .then((response) => res.send({ count: response.length }))
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
        "resourceMetadata.versions.0.timestamp": getDateQuery(
          req.query.startDate,
          req.query.endDate
        ),
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
        "resourceMetadata.versions.timestamp": getDateQuery(
          req.query.startDate,
          req.query.endDate
        ),
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

metricsRouter.get("/templateUsageCount", (req, res, next) => {
  req.db
    .collection("resources")
    .count({ templateId: req.query.templateId })
    .then((response) => res.send({ count: response }))
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
