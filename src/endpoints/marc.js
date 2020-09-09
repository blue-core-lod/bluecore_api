import express from 'express'
import { requestMarc, hasMarc, getMarc } from '../aws.js'
import { handleError, handleNotFound } from '../error.js'

const marcRouter = express.Router()

const apiBaseUrl = process.env.API_BASE_URL

// See https://jsonapi.org/recommendations/#asynchronous-processing
marcRouter.post('/:resourceId([^/]+/?[^/]+?)', (req, res) => {
  console.log(`Received post to ${req.params.resourceId} to generate MARC`)

  // Make sure the record exists.
  let findOnePromise
  if(process.env.NODE_ENV === 'development') {
    // In local development, Mongo may not exist or resource may not be in db.
    findOnePromise = Promise.resolve({
      uri: `https://api.development.sinopia.io/repository/${req.params.resourceId}`,
      id: req.params.resourceId,
      timestamp: new Date()
    })
  } else {
    findOnePromise = req.db.collection('resources').findOne({id: req.params.resourceId})
  }
  findOnePromise
    .then((resource) => {
      if(!resource) return handleNotFound(req.params.resourceId, res)
      const username = req.user['cognito:username']
      // Using the timestamp of the resource. This allows tying the MARC back to the specific resource version.
      const timestamp = resource.timestamp.toISOString()
      return requestMarc(resource.uri, resource.id, username, timestamp)
        .then(() => {
          res
            .set('Content-Location', marcJobUrlFor(req, username, timestamp))
            .sendStatus(202)
        })
        .catch(handleError(req, res))
    })
    .catch(handleError(req, res))
})

marcRouter.get('/:resourceId([^/]+/?[^/]+?)/job/:username/:timestamp', (req, res) => {
  return hasMarc(req.params.resourceId, req.params.username, req.params.timestamp)
    .then((marcExists) => {
      if (!marcExists) {
        return res.sendStatus(200)
      }
      return res.location(marcVersionUrlFor(req)).sendStatus(303)
    })
    .catch(handleError(req, res))
})

marcRouter.get('/:resourceId([^/]+/?[^/]+?)/version/:username/:timestamp', (req, res) => {
  res.format({
    'text/plain': () => {
      getMarc(req.params.resourceId, req.params.username, req.params.timestamp, true)
        .then((body) => res.type('text/plain').send(body))
        .catch(handleError(req, res))
    },
    'application/marc': () => {
      getMarc(req.params.resourceId, req.params.username, req.params.timestamp, false)
        .then((body) => res.type('application/marc').send(body))
        .catch(handleError(req, res))
    }
  })
})

const marcUrlFor = (req) => {
  const {resourceId} = req.params
  if(apiBaseUrl) return `${apiBaseUrl}/marc/${resourceId}`
  return `${req.protocol}://${req.hostname}:${req.port}/marc/${resourceId}`
}

const marcJobUrlFor = (req, username, timestamp) => {
  return `${marcUrlFor(req)}/job/${username}/${timestamp}`
}

const marcVersionUrlFor = (req) => {
  return `${marcUrlFor(req)}/version/${req.params.username}/${req.params.timestamp}`
}

export default marcRouter
