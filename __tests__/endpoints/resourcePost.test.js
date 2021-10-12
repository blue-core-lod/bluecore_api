import connect from "mongo.js"
import request from "supertest"
import app from "app.js"
import FakeTimers from "@sinonjs/fake-timers"
const resource = require("../__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json")
const resourceMetadata = require("../__fixtures__/metadata_6852a770-2961-4836-a833-0b21a9b68041.json")
const resBody = require("../__fixtures__/resp_6852a770-2961-4836-a833-0b21a9b68041.json")
const reqBody = require("../__fixtures__/req_6852a770-2961-4836-a833-0b21a9b68041.json")

// To avoid race conditions with mocking connect, testing of resources is split into
// Multiple files.

jest.mock("mongo.js")
jest.mock("jwt.js", () => {
  return {
    __esModule: true,
    default: jest
      .fn()
      .mockReturnValue({ secret: "shhhhhhared-secret", algorithms: ["HS256"] }),
  }
})
// This won't be required after Jest 27
jest.useFakeTimers("modern")

let clock
beforeAll(() => {
  clock = FakeTimers.install({ now: new Date("2020-08-20T11:34:40.887Z") })
})

afterAll(() => {
  clock.uninstall()
})

describe("POST /resource/:resourceId", () => {
  let mockResourcesInsert
  let mockResourceVersionsInsert
  let mockResourceMetadataInsert

  beforeEach(() => {
    mockResourcesInsert = jest.fn().mockResolvedValue()
    mockResourceVersionsInsert = jest.fn().mockResolvedValue()
    mockResourceMetadataInsert = jest.fn().mockResolvedValue()
    const mockCollection = (collectionName) => {
      return {
        resources: { insert: mockResourcesInsert },
        resourceVersions: { insert: mockResourceVersionsInsert },
        resourceMetadata: { insert: mockResourceMetadataInsert },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))
  })

  it("persists new resource", async () => {
    // Bearer eyJhbGciOiJIU... encodes stanford as the user's group.
    const res = await request(app)
      .post("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
      .send(reqBody)
    expect(res.statusCode).toEqual(201)
    expect(res.body).toEqual(resBody)
    expect(res.header.location).toEqual(
      "https://api.development.sinopia.io/resource/6852a770-2961-4836-a833-0b21a9b68041"
    )
    const saveResource = { ...resource }
    delete saveResource._id
    saveResource.timestamp = new Date()
    expect(mockResourcesInsert).toHaveBeenCalledWith(saveResource)
    expect(mockResourceVersionsInsert).toHaveBeenCalledWith(saveResource)

    const expectedResourceMetadata = { ...resourceMetadata }
    expectedResourceMetadata.versions[0].timestamp = new Date()
    expect(mockResourceMetadataInsert).toHaveBeenCalledWith(
      expectedResourceMetadata
    )
  })
  it("requires auth", async () => {
    const res = await request(app)
      .post("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .send(reqBody)
    expect(res.statusCode).toEqual(401)
  })
  it("requires permissions", async () => {
    const res = await request(app)
      .post("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
      .send({ ...reqBody, group: "cornell" })
    expect(res.statusCode).toEqual(401)
    expect(res.body).toEqual([
      {
        title: "Unauthorized",
        details: "User must a member of the resource's group",
        status: "401",
      },
    ])
  })
  it("returns 400 error if resource is unparseable jsonld", async () => {
    const reqBodyUnparseable = { ...reqBody, data: [{ "@context": "object" }] }
    const res = await request(app)
      .post("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
      .send(reqBodyUnparseable)
      .set("Content-Type", "application/json")
    expect(res.statusCode).toEqual(400)
    expect(res.body).toEqual([
      {
        title: "Bad Request",
        details: "Unparseable jsonld: Invalid context IRI: object",
        status: "400",
      },
    ])
  })
  it("returns 409 if resource is not unique", async () => {
    const err = new Error("Ooops")
    err.code = 11000
    mockResourcesInsert.mockRejectedValue(err)
    const res = await request(app)
      .post("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
      .send(reqBody)
    expect(res.statusCode).toEqual(409)
    expect(res.body).toEqual([
      {
        title: "Conflict",
        details: "ID is already in use. Please choose a unique ID.",
        status: "409",
      },
    ])
  })

  describe("permissions when NO_AUTH", () => {
    const ORIG_ENV = process.env

    beforeAll(() => {
      process.env = { ...ORIG_ENV, NO_AUTH: "true" }
    })

    afterAll(() => {
      process.env = ORIG_ENV
    })
    it("ignores permissions when NO_AUTH", async () => {
      const res = await request(app)
        .post("/resource/6852a770-2961-4836-a833-0b21a9b68041")
        .set(
          "Authorization",
          "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
        )
        .send({ ...reqBody, group: "cornell" })
      expect(res.statusCode).toEqual(201)
    })
  })

  describe("permissions when admin", () => {
    it("ignores permissions when admin", async () => {
      const res = await request(app)
        .post("/resource/6852a770-2961-4836-a833-0b21a9b68041")
        .set(
          "Authorization",
          "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbImFkbWluIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.6d5NChvKpK-lImFg3ZBSvlgqlI883vLDT9j_bI2AGtg"
        )
        .send({ ...reqBody, group: "cornell" })
      expect(res.statusCode).toEqual(201)
    })
  })
})
