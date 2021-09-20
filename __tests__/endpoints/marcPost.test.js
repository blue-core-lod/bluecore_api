import connect from "mongo.js"
import request from "supertest"
import app from "app.js"
import * as aws from "aws.js"
const resource = require("../__fixtures__/resource_6852a770-2961-4836-a833-0b21a9b68041.json")
resource.timestamp = new Date(resource.timestamp)

// To avoid race conditions with mocking connect, testing is split into
// Multiple files.

jest.mock("mongo.js")
jest.mock("aws.js")
jest.mock("jwt.js", () => {
  return {
    __esModule: true,
    default: jest
      .fn()
      .mockReturnValue({ secret: "shhhhhhared-secret", algorithms: ["HS256"] }),
  }
})

describe("POST /marc/:resourceId", () => {
  describe("resource found", () => {
    it("requests MARC and return job URL", async () => {
      const mockFindOne = jest.fn().mockResolvedValue(resource)
      const mockCollection = (collectionName) => {
        return {
          resources: { findOne: mockFindOne },
        }[collectionName]
      }
      const mockDb = { collection: mockCollection }
      connect.mockImplementation(mockConnect(mockDb))

      aws.requestMarc.mockResolvedValue()

      const res = await request(app)
        .post("/marc/6852a770-2961-4836-a833-0b21a9b68041")
        .set(
          "Authorization",
          "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMiwiY29nbml0bzp1c2VybmFtZSI6Impkb2UifQ.Rmfs_TH1hYeCcQrTmoOXxA3f0UC1yhgTRdYLUSmRw-c"
        )
        .send()
      expect(res.statusCode).toEqual(202)
      expect(res.header["content-location"]).toEqual(
        "https://api.development.sinopia.io/marc/6852a770-2961-4836-a833-0b21a9b68041/job/jdoe/2020-08-20T11:34:40.887Z"
      )
      expect(aws.requestMarc).toHaveBeenCalledWith(
        "https://api.development.sinopia.io/resource/6852a770-2961-4836-a833-0b21a9b68041",
        "6852a770-2961-4836-a833-0b21a9b68041",
        "jdoe",
        "2020-08-20T11:34:40.887Z"
      )
    })
  })
  describe("resource not found", () => {
    it("returns 404", async () => {
      const mockFindOne = jest.fn().mockResolvedValue(null)
      const mockCollection = (collectionName) => {
        return {
          resources: { findOne: mockFindOne },
        }[collectionName]
      }
      const mockDb = { collection: mockCollection }
      connect.mockImplementation(mockConnect(mockDb))

      const res = await request(app)
        .post("/marc/6852a770-2961-4836-a833-0b21a9b68041")
        .set(
          "Authorization",
          "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMiwiY29nbml0bzp1c2VybmFtZSI6Impkb2UifQ.Rmfs_TH1hYeCcQrTmoOXxA3f0UC1yhgTRdYLUSmRw-c"
        )
        .send()
      expect(res.statusCode).toEqual(404)
    })
  })
})
