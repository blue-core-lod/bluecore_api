import express from 'express'

const groupsRouter = express.Router()

groupsRouter.get('/', (req, res, next) => {
  req.db.collection('resources').distinct('group')
    .then((groups) => {
      res.send({
        data: groups.map((group) => ({id: group}))
      })
    })
    .catch(next)
})

export default groupsRouter
