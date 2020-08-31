import Honeybadger from 'honeybadger'

const hbKey = process.env.HONEYBADGER_API_KEY || 'abc123'

const HoneybadgerNotifier = Honeybadger.configure({
  apiKey: hbKey
})

export default HoneybadgerNotifier
