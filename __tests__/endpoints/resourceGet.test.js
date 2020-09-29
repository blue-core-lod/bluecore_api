import connect from 'mongo.js'
import request from 'supertest'
import app from 'app.js'
const resource = require('../__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json')
const resource2 = require('../__fixtures__/resource_63834c19-4d01-4c91-9dcc-a69c6e26c886.json')
const resBody = require('../__fixtures__/resp_6852a770-2961-4836-a833-0b21a9b68041.json')
const allResBody = require('../__fixtures__/all_resp.json')
const pageOneResBody = require('../__fixtures__/page_one_resp.json')

// To avoid race conditions with mocking connect, testing of resources is split into
// Multiple files.

jest.mock('mongo.js')

// GET all resources
describe('GET /resource/', () => {

  it('returns all of the available resources', async () => {
    /* eslint-disable callback-return */
    const mockEvery = jest.fn().mockImplementation((callback) => {
      callback(resource)
      callback(resource2)
      return Promise.resolve()
    })
    /* eslint-enable callback-return */
    const mockFind = jest.fn().mockReturnValue({each: mockEvery})
    const mockCollection = (collectionName) => {
      return {
        resources: {find: mockFind}
      }[collectionName]
    }
    const mockDb = {collection: mockCollection}
    connect.mockReturnValue(mockDb)

    const res = await request(app)
      .get('/resource/')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual(allResBody)
    expect(mockFind).toHaveBeenCalledWith({}, {"limit": 26, "skip": 0})
  })

  it('returns the first page with one resource', async () => {
    /* eslint-disable callback-return */
    const mockEvery = jest.fn().mockImplementation((callback) => {
      callback(resource)
      callback(resource2)
      return Promise.resolve()
    })
    /* eslint-enable callback-return */
    const mockFind = jest.fn().mockReturnValue({each: mockEvery})
    const mockCollection = (collectionName) => {
      return {
        resources: {find: mockFind}
      }[collectionName]
    }
    const mockDb = {collection: mockCollection}
    connect.mockReturnValue(mockDb)

    const res = await request(app)
      .get('/resource?limit=1&start=1')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual(pageOneResBody)
    // Note that limit is always the query limit+1 and skip = start-1
    expect(mockFind).toHaveBeenCalledWith({}, {"limit": 2, "skip": 0})
  })

  it('returns the second page with one resource and all links', async () => {
    const firstLink = 'https://api.development.sinopia.io/resource?limit=0&start=1'
    const nextLink = 'https://api.development.sinopia.io/resource?limit=1&start=3'
    const prevLink = 'https://api.development.sinopia.io/resource?limit=1&start=1'

    /* eslint-disable callback-return */
    const mockEvery = jest.fn().mockImplementation((callback) => {
      callback(resource)
      callback(resource2)
      return Promise.resolve()
    })
    /* eslint-enable callback-return */
    const mockFind = jest.fn().mockReturnValue({each: mockEvery})
    const mockCollection = (collectionName) => {
      return {
        resources: {find: mockFind}
      }[collectionName]
    }
    const mockDb = {collection: mockCollection}
    connect.mockReturnValue(mockDb)

    const res = await request(app)
      .get('/resource?limit=1&start=2')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(200)
    const bodyString = JSON.stringify(res.body)
    expect(bodyString).toMatch(firstLink)
    expect(bodyString).toMatch(nextLink)
    expect(bodyString).toMatch(prevLink)
    // Note that limit is always the query limit+1 and skip = start-1
    expect(mockFind).toHaveBeenCalledWith({}, {"limit": 2, "skip": 1})
  })

  it('constructs a query from querystring', async () => {
    /* eslint-disable callback-return */
    const mockEvery = jest.fn().mockImplementation((callback) => {
      callback(resource)
      callback(resource2)
      return Promise.resolve()
    })
    /* eslint-enable callback-return */
    const mockFind = jest.fn().mockReturnValue({each: mockEvery})
    const mockCollection = (collectionName) => {
      return {
        resources: {find: mockFind}
      }[collectionName]
    }
    const mockDb = {collection: mockCollection}
    connect.mockReturnValue(mockDb)

    const res = await request(app)
      .get('/resource/?group=stanford&type=http://id.loc.gov/ontologies/bibframe/AdminMetadata&updatedAfter=2019-11-08T17:40:23.363Z&updatedBefore=2020-11-08T17:40:23.363Z')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(200)
    const bodyString = JSON.stringify(res.body)
    const firstLink = 'https://api.development.sinopia.io/resource?limit=0&start=25&group=stanford&type=http://id.loc.gov/ontologies/bibframe/AdminMetadata&updatedAfter=2019-11-08T17:40:23.363Z&updatedBefore=2020-11-08T17:40:23.363Z'
    expect(bodyString).toMatch(firstLink)
    expect(mockFind).toHaveBeenCalledWith({
      group: 'stanford',
      types: 'http://id.loc.gov/ontologies/bibframe/AdminMetadata',
      timestamp: { $gte: new Date('2019-11-08T17:40:23.363Z'), $lte: new Date('2020-11-08T17:40:23.363Z')},
    }, {
      limit: 26,
      skip: 0,
    })
  })

  it('returns 400 for invalid date', async () => {
    const res = await request(app)
      .get('/resource/?updatedBefore=yesterday')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(400)
    expect(res.body).toEqual([
      {
        title: 'Bad Request',
        details: 'Error: Invalid date-time: yesterday',
        code: '400'
      }
    ])
  })
})

// GET a single resource
describe('GET /resource/:resourceId', () => {
  it('returns the resource', async () => {
    const mockFindOne = jest.fn().mockResolvedValue(resource)
    const mockCollection = (collectionName) => {
      return {
        resources: {findOne: mockFindOne}
      }[collectionName]
    }
    const mockDb = {collection: mockCollection}
    connect.mockReturnValue(mockDb)

    const res = await request(app)
      .get('/resource/6852a770-2961-4836-a833-0b21a9b68041')
      .set('Accept', 'application/json')
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual(resBody)
    expect(mockFindOne).toHaveBeenCalledWith({id: '6852a770-2961-4836-a833-0b21a9b68041'})
  })
})
