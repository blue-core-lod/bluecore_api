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
  // This is reached by sending a value of "all" which is contrained by openapi
  return null
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

export default metricsRouter
