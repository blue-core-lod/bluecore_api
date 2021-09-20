import connect from "mongo.js"
import request from "supertest"
import app from "app.js"

jest.mock("mongo.js")
jest.mock("jwt.js", () => {
  return {
    __esModule: true,
    default: jest
      .fn()
      .mockReturnValue({ secret: "shhhhhhared-secret", algorithms: ["HS256"] }),
  }
})

describe("DELETE /resource/:resourceId", () => {
  const mockResourceDelete = jest.fn().mockResolvedValue({ deletedCount: 1 })
  const mockResourceVersionsDelete = jest.fn().mockResolvedValue()
  const mockResourceMetadataDelete = jest.fn().mockResolvedValue()
  const mockFindOne = jest.fn().mockResolvedValue({ group: "stanford" })

  const mockCollection = (collectionName) => {
    return {
      resources: { remove: mockResourceDelete, findOne: mockFindOne },
      resourceVersions: { remove: mockResourceVersionsDelete },
      resourceMetadata: { remove: mockResourceMetadataDelete },
    }[collectionName]
  }
  const mockDb = { collection: mockCollection }
  connect.mockImplementation(mockConnect(mockDb))

  it("removes existing resource", async () => {
    const res = await request(app)
      .delete("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
    expect(res.statusCode).toEqual(204)
    expect(mockResourceDelete).toHaveBeenCalledWith({
      id: "6852a770-2961-4836-a833-0b21a9b68041",
    })
    expect(mockResourceVersionsDelete).toHaveBeenCalledWith({
      id: "6852a770-2961-4836-a833-0b21a9b68041",
    })
    expect(mockResourceMetadataDelete).toHaveBeenCalledWith({
      id: "6852a770-2961-4836-a833-0b21a9b68041",
    })
    expect(mockFindOne).toHaveBeenCalledWith(
      { id: "6852a770-2961-4836-a833-0b21a9b68041" },
      { projection: { group: 1 } }
    )
  })

  it("requires auth", async () => {
    const res = await request(app).delete(
      "/resource/6852a770-2961-4836-a833-0b21a9b68041"
    )
    expect(res.statusCode).toEqual(401)
  })

  it("requires permissions", async () => {
    mockFindOne.mockResolvedValue({ group: "cornell" })
    const res = await request(app)
      .delete("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.L-nq_acWpTf-aZsaN0tNL_kXTrasxoTSxUAgMUVlgaU"
      )
    expect(res.statusCode).toEqual(401)
    expect(res.body).toEqual([
      {
        title: "Unauthorized",
        details: "User must a member of the resource's group",
        status: "401",
      },
    ])
  })

  it("returns 404 when resource does not exist", async () => {
    mockFindOne.mockResolvedValue(null)
    const res = await request(app)
      .delete("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg"
      )
    expect(res.statusCode).toEqual(404)
    expect(res.body).toEqual([
      {
        title: "Not Found",
        status: "404",
      },
    ])
  })
})
