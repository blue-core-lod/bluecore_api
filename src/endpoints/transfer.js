import express from "express"
import { buildAndSendSqsMessage } from "../aws.js"
import { canTransfer } from "../permissions.js"
import { resourceUriFor } from "./resourcesHelpers.js"

const transferRouter = express.Router()

transferRouter.post(
  [
    "/:resourceId/:targetGroup/:targetSystem/:targetResourceId",
    "/:resourceId/:targetGroup/:targetSystem",
  ],
  [
    canTransfer,
    (req, res, next) => {
      const { resourceId, targetGroup, targetSystem, targetResourceId } =
        req.params
      console.log(
        `transferRouter Received post to /${resourceId}/${targetGroup}/${targetSystem}`
      )

      const sqsMessageBody = {
        resource: { uri: resourceUriFor(req) },
        user: {
          email: req.user.email,
        },
        group: targetGroup,
        target: targetSystem,
        targetResourceId,
      }

      const queueName = `${targetGroup}-${targetSystem}`
      buildAndSendSqsMessage(queueName, JSON.stringify(sqsMessageBody))
        .then(() => {
          res.sendStatus(204)
        })
        .catch(next)
    },
  ]
)

export default transferRouter
