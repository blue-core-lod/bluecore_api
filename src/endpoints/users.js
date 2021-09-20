import express from "express"
import _ from "lodash"
import connect from "../mongo.js"

const usersRouter = express.Router()

const apiBaseUrl = process.env.API_BASE_URL
const historySize = {
  resource: Number(process.env.RESOURCE_HISTORY_SIZE) || 10,
  template: Number(process.env.TEMPLATE_HISTORY_SIZE) || 10,
  search: Number(process.env.SEARCH_HISTORY_SIZE) || 10,
}

// Add the db to req
usersRouter.use(connect)

usersRouter.post("/:userId", (req, res, next) => {
  console.log(`Received post to ${req.params.userId}`)

  const userUri = userUriFor(req)
  const userData = {
    id: req.params.userId,
    data: { history: { resource: [], template: [], search: [] } },
  }
  req.db
    .collection("users")
    .insert(userData)
    .then(() => res.location(userUri).status(201).send(forReturn(userData)))
    .catch(next)
})

usersRouter.get("/:userId", (req, res, next) => {
  req.db
    .collection("users")
    .findOne({ id: req.params.userId })
    .then((userData) => {
      if (!userData) return res.sendStatus(404)
      return res.send(forReturn(userData))
    })
    .catch(next)
})

usersRouter.put(
  "/:userId/history/:historyType(resource|template|search)/:historyItemId",
  (req, res, next) => {
    const { historyType } = req.params
    console.log(
      `Received post to ${req.params.userId}/history/${historyType}/${req.params.historyItemId}`
    )

    const { payload } = req.body

    req.db
      .collection("users")
      .findOne({ id: req.params.userId })
      .then((userData) => {
        if (!userData) return res.sendStatus(404)
        const newEntry = { id: req.params.historyItemId, payload }
        const filteredEntries = userData.data.history[historyType].filter(
          (entry) => entry.id !== req.params.historyItemId
        )
        const newHistory = [newEntry, ...filteredEntries].slice(
          0,
          historySize[historyType]
        )
        if (_.isEqual(newHistory, userData.data.history[historyType]))
          return res.send(forReturn(userData))

        userData.data.history[historyType] = newHistory

        req.db
          .collection("users")
          .update({ id: req.params.userId }, userData, { replaceOne: true })
          .then(() => {
            return res.send(forReturn(userData))
          })
          .catch(next)
      })
      .catch(next)
  }
)

const forReturn = (item) => {
  const newItem = { ...item }
  delete newItem._id
  return newItem
}

const userUriFor = (req) => {
  return `${baseUrlFor(req)}/${req.params.userId}`
}

const baseUrlFor = (req) => {
  if (apiBaseUrl) return `${apiBaseUrl}/user`
  return `${req.protocol}://${req.hostname}:${req.port}/user`
}

export default usersRouter
