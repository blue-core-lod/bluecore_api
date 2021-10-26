import express from "express"
import { listGroups } from "../aws.js"

const groupsRouter = express.Router()

groupsRouter.get("/", (req, res, next) => {
  // Filter out admin group
  listGroups()
    .then((groups) => groups.filter((group) => group.id !== "admin"))
    .then((groups) => res.json({ data: groups }))
    .catch(next)
})

export default groupsRouter
