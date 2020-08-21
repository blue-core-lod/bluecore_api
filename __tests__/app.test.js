import request from 'supertest'
import app from 'app.js'

jest.mock('mongo.js')

describe('GET /', () => {
  it('returns health check', async () => {
    const res = await request(app).get('/')
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual({ all: 'good' })
  })
})
