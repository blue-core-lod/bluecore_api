import connect from 'mongo.js'
import request from 'supertest'
import app from 'app.js'
import FakeTimers from '@sinonjs/fake-timers'
import createError from 'http-errors'

const resource = require('../__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json')
const resBody = require('../__fixtures__/resp_6852a770-2961-4836-a833-0b21a9b68041.json')
const reqBody = require('../__fixtures__/req_6852a770-2961-4836-a833-0b21a9b68041.json')

// To avoid race conditions with mocking connect, testing of resources is split into
// Multiple files.

jest.mock('mongo.js')
jest.mock('jwt.js', () => {
  return {
    __esModule: true,
    default: jest.fn().mockReturnValue({ secret: 'shhhhhhared-secret', algorithms: ['HS256'] })
  }
})
// This won't be required after Jest 27
jest.useFakeTimers('modern')

let clock
beforeAll(() => {
  clock = FakeTimers.install({now: new Date('2020-08-20T11:34:40.887Z')})
})

afterAll(() => {
  clock.uninstall()
})

describe('PUT /resource/:resourceId', () => {
  const mockResourcesUpdate = jest.fn().mockResolvedValue({nModified: 1})
  const mockResourceVersionsInsert = jest.fn().mockResolvedValue()
  const mockResourceMetadataUpdate = jest.fn().mockResolvedValue()
  const mockCollection = (collectionName) => {
    return {
      resources: {update: mockResourcesUpdate},
      resourceVersions: {insert: mockResourceVersionsInsert},
      resourceMetadata: {update: mockResourceMetadataUpdate}
    }[collectionName]
  }
  const mockDb = {collection: mockCollection}
  connect.mockReturnValue(mockDb)

  it('updates existing resource', async () => {
    const res = await request(app)
      .put('/resource/6852a770-2961-4836-a833-0b21a9b68041')
      .set('Authorization', 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg')
      .send(reqBody)
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual(resBody)
    const saveResource = {...resource}
    delete saveResource._id
    saveResource.timestamp = new Date()
    expect(mockResourcesUpdate).toHaveBeenCalledWith({id: '6852a770-2961-4836-a833-0b21a9b68041'}, saveResource, {replaceOne: true})
    expect(mockResourceVersionsInsert).toHaveBeenCalledWith(saveResource)

    const versionEntry = {
      "timestamp": new Date(),
      "user": "havram",
      "group": "stanford",
      "editGroups": ["stanford"],
      "templateId": "profile:bf2:Title:AbbrTitle"
    }
    expect(mockResourceMetadataUpdate).toHaveBeenCalledWith({id: '6852a770-2961-4836-a833-0b21a9b68041'}, { $push: { versions: versionEntry}})
  })
  it('requires auth', async () => {
    const res = await request(app)
      .put('/resource/6852a770-2961-4836-a833-0b21a9b68041')
      .send(reqBody)
    expect(res.statusCode).toEqual(401)
  })
  it('returns 400 error if resource is unparseable', async () => {
    const reqBodyUnparseable = String(reqBody).replace('"@value"', '"@value')
    const res = await request(app)
      .post('/resource/6852a770-2961-4836-a833-0b21a9b68041')
      .set('Authorization', 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg')
      .send(reqBodyUnparseable)
      .set('Content-Type', 'application/json')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(400)
    expect(res.body).toEqual([
      {
        title: 'Bad Request',
        details: 'Unexpected token o in JSON at position 1',
        status: '400',
      }
    ])
  })
  it('returns 404 when resource does not exist', async () => {
    mockResourcesUpdate.mockRejectedValue(new createError.NotFound())
    const res = await request(app)
      .put('/resource/6852a770-2961-4836-a833-0b21a9b68041')
      .set('Authorization', 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg')
      .send(reqBody)
    expect(res.statusCode).toEqual(404)
    expect(res.body).toEqual([
      {
        title: 'Not Found',
        status: '404'
      }
    ])
  })
})
