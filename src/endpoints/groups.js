import express from 'express'

const groupsRouter = express.Router()

groupsRouter.get('/', (req, res) => {
  req.db.collection('resources').distinct('group')
    .then((groups) => {
      res.send({
        data: groups.map((group) => ({id: group}))
      })
    })
})

export default groupsRouter
