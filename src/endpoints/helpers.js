import express from "express"
import { detectLanguage } from "../aws.js"

const helperRouter = express.Router()

helperRouter.post("/langDetection", (req, res, next) => {
  const query = req.body
  detectLanguage(query)
    .then((languages) => {
      res.send({
        query,
        data: languages,
      })
    })
    .catch(next)
})

export default helperRouter
