import connect from "mongo.js"
import request from "supertest"
import app from "app.js"
import createError from "http-errors"

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
  const mockCollection = (collectionName) => {
    return {
      resources: { remove: mockResourceDelete },
      resourceVersions: { remove: mockResourceVersionsDelete },
      resourceMetadata: { remove: mockResourceMetadataDelete },
    }[collectionName]
  }
  const mockDb = { collection: mockCollection }
  connect.mockReturnValue(mockDb)

  it("removes existing resource", async () => {
    const res = await request(app)
      .delete("/resource/6852a770-2961-4836-a833-0b21a9b68041")
      .set(
        "Authorization",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.fLGW-NqeXUex3gZpZW0e61zP5dmhmjNPCdBikj_7Djg"
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
  })

  it("requires auth", async () => {
    const res = await request(app).delete(
      "/resource/6852a770-2961-4836-a833-0b21a9b68041"
    )
    expect(res.statusCode).toEqual(401)
  })

  it("returns 404 when resource does not exist", async () => {
    mockResourceDelete.mockRejectedValue(new createError.NotFound())
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
