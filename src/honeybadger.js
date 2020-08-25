import Honeybadger from 'honeybadger'

const hb_key = process.env.HONEYBADGER_API_KEY || 'abc123'

const HoneybadgerNotifier = Honeybadger.configure({
  apiKey: hb_key
})

export default HoneybadgerNotifier
