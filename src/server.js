import app from './app.js'
import honeybadger from 'honeybadger'

const hb_key = process.env.HONEYBADGER_API_KEY || 'afb5bf85'
honeybadger.configure({
  apiKey: hb_key
});

const port = process.env.PORT || 3000
app.listen(port, () => {
  console.log(`listening on ${port}`)
})
