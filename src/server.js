import app from './app.js'
import HoneybadgerNotifier from './honeybadger.js'

const port = process.env.PORT || 3000
app.listen(port, () => {
  console.log(`listening on ${port}`)
})

// Use *after* all other app middleware.
app.use(HoneybadgerNotifier.errorHandler)
