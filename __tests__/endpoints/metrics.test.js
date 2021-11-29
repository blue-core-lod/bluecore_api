import connect from "mongo.js"
import request from "supertest"
import app from "app.js"

jest.mock("mongo.js")

const response = { count: 1 }
const mockAggregateResponse = jest.fn().mockResolvedValue([response])
const mockResponse = jest.fn().mockResolvedValue(1)

const allResourceQuery = {
  types: { $regex: ".*" },
}
const templateOnlyQuery = {
  types: "http://sinopia.io/vocabulary/ResourceTemplate",
}
const resourceOnlyQuery = {
  types: {
    $not: { $eq: "http://sinopia.io/vocabulary/ResourceTemplate" },
  },
}

describe("GET /metrics/userCount", () => {
  it("returns the total user count", async () => {
    const mockCollection = (collectionName) => {
      return {
        users: { count: mockResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/metrics/userCount")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
  })
})

describe("GET /metrics/resourceCount", () => {
  it("returns the total resource count when user asks for 'all'", async () => {
    const mockCollection = (collectionName) => {
      return {
        resources: { count: mockResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/metrics/resourceCount/all")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
    expect(mockResponse).toHaveBeenCalledWith(allResourceQuery)
  })

  it("returns the just the resource templates resource count when user asks for 'template'", async () => {
    const mockCollection = (collectionName) => {
      return {
        resources: { count: mockResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/metrics/resourceCount/template")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
    expect(mockResponse).toHaveBeenCalledWith(templateOnlyQuery)
  })

  it("returns the just the resources count when user asks for 'resource'", async () => {
    const mockCollection = (collectionName) => {
      return {
        resources: { count: mockResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/metrics/resourceCount/resource")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
    expect(mockResponse).toHaveBeenCalledWith(resourceOnlyQuery)
  })
})

describe("GET /metrics/createdCount", () => {
  it("adds correct filters for date and resource type", async () => {
    const mockCollection = (collectionName) => {
      return {
        resources: { aggregate: mockAggregateResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get("/metrics/createdCount/all?startDate=2021-10-01&endDate=2021-11-01")
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
    // The resource type filter
    expect(mockAggregateResponse.mock.calls[0][0][0]).toEqual({
      $match: allResourceQuery,
    })
    // The date filter
    expect(mockAggregateResponse.mock.calls[0][0][3]).toEqual({
      $match: {
        "resourceMetadata.versions.0.timestamp": {
          $gt: new Date("2021-10-01"),
          $lt: new Date("2021-11-01"),
        },
      },
    })
  })

  it("adds group filter when requested", async () => {
    const mockCollection = (collectionName) => {
      return {
        resources: { aggregate: mockAggregateResponse },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get(
        "/metrics/createdCount/resource?startDate=2021-01-01&endDate=2021-12-31&group=stanford"
      )
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual(response)
    // The resource type filter with group added
    const groupFilter = resourceOnlyQuery
    groupFilter.group = "stanford"
    expect(mockAggregateResponse.mock.calls[0][0][0]).toEqual({
      $match: groupFilter,
    })
    // The date filter
    expect(mockAggregateResponse.mock.calls[0][0][3]).toEqual({
      $match: {
        "resourceMetadata.versions.0.timestamp": {
          $gt: new Date("2021-01-01"),
          $lt: new Date("2021-12-31"),
        },
      },
    })
  })

  it("responds correctly with no mongo results (empty array)", async () => {
    const mockCollection = (collectionName) => {
      return {
        resources: { aggregate: jest.fn().mockResolvedValue([]) },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))

    const res = await request(app)
      .get(
        "/metrics/createdCount/resource?startDate=2021-01-01&endDate=2021-12-31&group=stanford"
      )
      .set("Accept", "application/json")
    expect(res.statusCode).toEqual(200)
    expect(res.type).toEqual("application/json")
    expect(res.body).toEqual({ count: 0 })
  })
})
