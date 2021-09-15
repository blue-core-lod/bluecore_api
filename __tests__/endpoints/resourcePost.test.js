import connect from 'mongo.js'
import request from 'supertest'
import app from 'app.js'
import FakeTimers from '@sinonjs/fake-timers'
const resource = require('../__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json')
const resourceMetadata = require('../__fixtures__/metadata_6852a770-2961-4836-a833-0b21a9b68041.json')
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

describe('POST /resource/:resourceId', () => {
  const mockResourcesInsert = jest.fn().mockResolvedValue()
  const mockResourceVersionsInsert = jest.fn().mockResolvedValue()
  const mockResourceMetadataInsert = jest.fn().mockResolvedValue()
  const mockCollection = (collectionName) => {
    return {
      resources: {insert: mockResourcesInsert},
      resourceVersions: {insert: mockResourceVersionsInsert},
      resourceMetadata: {insert: mockResourceMetadataInsert}
    }[collectionName]
  }
  const mockDb = {collection: mockCollection}
  connect.mockReturnValue(mockDb)

  it('persists new resource', async () => {
    const res = await request(app)
      .post('/resource/6852a770-2961-4836-a833-0b21a9b68041')
      .set('Authorization', 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg')
      .send(reqBody)
    expect(res.statusCode).toEqual(201)
    expect(res.body).toEqual(resBody)
    expect(res.header.location).toEqual('https://api.development.sinopia.io/resource/6852a770-2961-4836-a833-0b21a9b68041')
    const saveResource = {...resource}
    delete saveResource._id
    saveResource.timestamp = new Date()
    expect(mockResourcesInsert).toHaveBeenCalledWith(saveResource)
    expect(mockResourceVersionsInsert).toHaveBeenCalledWith(saveResource)

    const expectedResourceMetadata = {...resourceMetadata}
    expectedResourceMetadata.versions[0].timestamp = new Date()
    expect(mockResourceMetadataInsert).toHaveBeenCalledWith(expectedResourceMetadata)
  })
  it('requires auth', async () => {
    const res = await request(app)
      .post('/resource/6852a770-2961-4836-a833-0b21a9b68041')
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
  it('returns 409 if resource is not unique', async () => {
    const err = new Error('Ooops')
    err.code = 11000
    mockResourcesInsert.mockRejectedValue(err)
    const res = await request(app)
      .post('/resource/6852a770-2961-4836-a833-0b21a9b68041')
      .set('Authorization', 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg')
      .send(reqBody)
    expect(res.statusCode).toEqual(409)
    expect(res.body).toEqual([
      {
        title: 'Conflict',
        details: 'Id is not unique',
        status: '409'
      }
    ])
  })
})
