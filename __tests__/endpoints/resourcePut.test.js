import connect from "mongo.js"
import request from "supertest"
import app from "app.js"
import FakeTimers from "@sinonjs/fake-timers"
import createError from "http-errors"

const resource = require("../__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json")
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

describe("PUT /resource/:resourceId", () => {
  let mockResourcesUpdate
  let mockResourceVersionsInsert
  let mockResourceMetadataUpdate
  let mockResourceMetadataFindOne

  beforeEach(() => {
    mockResourcesUpdate = jest.fn().mockResolvedValue({ nModified: 1 })
    mockResourceVersionsInsert = jest.fn().mockResolvedValue()
    mockResourceMetadataUpdate = jest.fn().mockResolvedValue()
    mockResourceMetadataFindOne = jest.fn().mockResolvedValue({
      versions: [{ group: "stanford", editGroups: ["yale"] }],
    })
    const mockCollection = (collectionName) => {
      return {
        resources: { update: mockResourcesUpdate },
        resourceVersions: { insert: mockResourceVersionsInsert },
        resourceMetadata: {
          update: mockResourceMetadataUpdate,
          findOne: mockResourceMetadataFindOne,
        },
      }[collectionName]
    }
    const mockDb = { collection: mockCollection }
    connect.mockImplementation(mockConnect(mockDb))
  })

  it("updates existing resource when user is member of owner group", async () => {
    // Bearer eyJhbGciOiJIU... encodes stanford as the user's group.
    const res = await request(app)
      .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
      .send(reqBody)
    expect(res.statusCode).toEqual(200)
    expect(res.body).toEqual(resBody)
    const saveResource = { ...resource }
    delete saveResource._id
    saveResource.timestamp = new Date()
    expect(mockResourcesUpdate).toHaveBeenCalledWith(
      { id: "6852a770-2961-4836-a833-0b21a9b68041" },
      saveResource,
      { replaceOne: true }
    )
    expect(mockResourceVersionsInsert).toHaveBeenCalledWith(saveResource)

    const versionEntry = {
      timestamp: new Date(),
      user: "havram",
      group: "stanford",
      editGroups: ["yale"],
      templateId: "profile:bf2:Title:AbbrTitle",
    }
    expect(mockResourceMetadataUpdate).toHaveBeenCalledWith(
      { id: "6852a770-2961-4836-a833-0b21a9b68041" },
      { $push: { versions: versionEntry } }
    )

    expect(mockResourceMetadataFindOne).toHaveBeenCalledWith(
      { id: "6852a770-2961-4836-a833-0b21a9b68041" },
      { projection: { versions: { $slice: -1 } } }
    )
  })
  it("updates existing resource when user is member of edit group", async () => {
    // Bearer eyJhbGciOiJIU... encodes stanford and pcc as the user's group.
    const res = await request(app)
      .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIiwicGNjIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.AtnKOR0bghI-DTjeWUTnLlNub1wc0QzAprrQQ2XGWR8"
      )
      .send({ ...reqBody, group: "pcc", editGroups: ["stanford"] })
    expect(res.statusCode).toEqual(200)
  })
  it("updates groups for existing resource when user is member of owner group", async () => {
    const res = await request(app)
      .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
      .send({ ...reqBody, editGroups: ["pcc"] })
    expect(res.statusCode).toEqual(200)
  })
  it("requires auth", async () => {
    const res = await request(app)
      .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .send(reqBody)
    expect(res.statusCode).toEqual(401)
  })
  it("requires permission to edit when user is not member of group or edit groups", async () => {
    // Bearer eyJhbGciOiJIU... encodes cornell as the user's group.
    // Cornell is not owner (stanford) or edit group ([yale]).
    const res = await request(app)
      .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbImNvcm5lbGwiXSwiZW1haWxfdmVyaWZpZWQiOnRydWUsImV2ZW50X2lkIjoiZTRhYzY4MDgtZWJhNS00MzYwLThlNTUtNjRlZTBiN2FmOWViIiwidG9rZW5fdXNlIjoiaWQiLCJhdXRoX3RpbWUiOjE2MzE5MTAzODAsImlzcyI6Imh0dHBzOi8vY29nbml0by1pZHAudXMtd2VzdC0yLmFtYXpvbmF3cy5jb20vdXMtd2VzdC0yX0NHZDlXcTEzNiIsImNvZ25pdG86dXNlcm5hbWUiOiJqbGl0dG1hbiIsImV4cCI6MjYzMjAwNzE0OCwiaWF0IjoxNjMyMDAzNTQ4LCJlbWFpbCI6Imp1c3RpbmxpdHRtYW5Ac3RhbmZvcmQuZWR1In0.bvW7W_CU6w20HBEMoua0SZdNcZGxA8_WG0E67lIlHdE"
      )
      .send(reqBody)
    expect(res.statusCode).toEqual(401)
    expect(res.body).toEqual([
      {
        title: "Unauthorized",
        details: "User must a member of the resource's group or editGroups",
        status: "401",
      },
    ])
  })
  it("requires permissions to change group when user is not a member of new group", async () => {
    // User is a member of stanford, not pcc.
    const res = await request(app)
      .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
      .send({ ...reqBody, group: "pcc" })
    expect(res.statusCode).toEqual(401)
    expect(res.body).toEqual([
      {
        title: "Unauthorized",
        details: "User must a member of the new group",
        status: "401",
      },
    ])
  })
  it("requires permissions to change group when user is not a member of resource group", async () => {
    // Bearer eyJhbGciOiJIU... encodes cornell as the user's group.
    // Cornell is not owner (stanford).
    const res = await request(app)
      .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbImNvcm5lbGwiXSwiZW1haWxfdmVyaWZpZWQiOnRydWUsImV2ZW50X2lkIjoiZTRhYzY4MDgtZWJhNS00MzYwLThlNTUtNjRlZTBiN2FmOWViIiwidG9rZW5fdXNlIjoiaWQiLCJhdXRoX3RpbWUiOjE2MzE5MTAzODAsImlzcyI6Imh0dHBzOi8vY29nbml0by1pZHAudXMtd2VzdC0yLmFtYXpvbmF3cy5jb20vdXMtd2VzdC0yX0NHZDlXcTEzNiIsImNvZ25pdG86dXNlcm5hbWUiOiJqbGl0dG1hbiIsImV4cCI6MjYzMjAwNzE0OCwiaWF0IjoxNjMyMDAzNTQ4LCJlbWFpbCI6Imp1c3RpbmxpdHRtYW5Ac3RhbmZvcmQuZWR1In0.bvW7W_CU6w20HBEMoua0SZdNcZGxA8_WG0E67lIlHdE"
      )
      .send({ ...reqBody, editGroups: ["pcc"] })
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
      .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
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
  it("returns 404 when resource does not exist", async () => {
    mockResourcesUpdate.mockRejectedValue(new createError.NotFound())
    const res = await request(app)
      .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
      .send(reqBody)
    expect(res.statusCode).toEqual(404)
    expect(res.body).toEqual([
      {
        title: "Not Found",
        status: "404",
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
      // User is a member of stanford, not pcc.
      const res = await request(app)
        .put("/resource/6852a770-2961-4836-a833-0b21a9b68041")
        .set(
          "Authorization",
          "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
        )
        .send({ ...reqBody, group: "pcc" })
      expect(res.statusCode).toEqual(200)
    })
  })
})
