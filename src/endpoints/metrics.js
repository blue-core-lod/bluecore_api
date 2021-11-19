import express from "express"
import connect from "../mongo.js"

const metricsRouter = express.Router()

// Add the db to req
metricsRouter.use(connect)

metricsRouter.get("/userCount", (req, res, next) => {
  req.db
    .collection("users")
    .count()
    .then((response) => res.send({ count: response }))
    .catch(next)
})

export default metricsRouter
