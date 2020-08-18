import request from 'supertest'
import app from 'app.js'
import * as mongo from 'mongo.js'

jest.mock('mongo.js')

// See https://stackoverflow.com/questions/48022742/how-to-mock-dynamical-for-mongodb-method
beforeEach(() => {
    mongo.connect.mockImplementation(() => Promise.resolve(null))
})

describe('/', () => {
  it('returns health check', async () => {
    const res = await request(app).get('/')
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual({ all: 'good' })
  })
})
