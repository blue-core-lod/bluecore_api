import express from "express"
import { listGroups } from "../aws.js"

const groupsRouter = express.Router()

groupsRouter.get("/", (req, res, next) => {
  listGroups()
    .then((groups) => res.json({ data: groups }))
    .catch(next)
})

export default groupsRouter
