import request from "supertest"
import app from "app.js"
import * as aws from "aws.js"

jest.mock("mongo.js")
jest.mock("aws.js")

describe("GET /:resourceId/job/:username/:timestamp", () => {
  describe("MARC does not exist", () => {
    it("returns 200", async () => {
      aws.hasMarc.mockResolvedValue(false)

      const res = await request(app).get(
        "/marc/6852a770-2961-4836-a833-0b21a9b68041/job/jdoe/2020-08-20T11:34:40.887Z"
      )
      expect(res.statusCode).toEqual(200)
      expect(aws.hasMarc).toHaveBeenCalledWith(
        "6852a770-2961-4836-a833-0b21a9b68041",
        "jdoe",
        "2020-08-20T11:34:40.887Z"
      )
    })
  })

  describe("MARC exists", () => {
    it("returns MARC url", async () => {
      aws.hasMarc.mockResolvedValue(true)

      const res = await request(app).get(
        "/marc/6852a770-2961-4836-a833-0b21a9b68041/job/jdoe/2020-08-20T11:34:40.887Z"
      )
      expect(res.statusCode).toEqual(303)
      expect(res.header.location).toEqual(
        "https://api.development.sinopia.io/marc/6852a770-2961-4836-a833-0b21a9b68041/version/jdoe/2020-08-20T11:34:40.887Z"
      )
    })
  })

  describe("job error", () => {
    it("returns error", async () => {
      aws.hasMarc.mockRejectedValue(new Error("Conversion failed"))
      const res = await request(app).get(
        "/marc/6852a770-2961-4836-a833-0b21a9b68041/job/jdoe/2020-08-20T11:34:40.887Z"
      )
      expect(res.statusCode).toEqual(500)
      expect(res.body).toEqual([
        { status: "500", details: "Conversion failed", title: "Server error" },
      ])
    })
  })
})

describe("GET /:resourceId/version/:username/:timestamp", () => {
  describe("requesting MARC", () => {
    aws.getMarc.mockResolvedValue("MARC record")
    it("returns MARC", async () => {
      const res = await request(app)
        .get(
          "/marc/6852a770-2961-4836-a833-0b21a9b68041/version/jdoe/2020-08-20T11:34:40.887Z"
        )
        .set("Accept", "application/marc")
      expect(res.statusCode).toEqual(200)
      expect(res.type).toEqual("application/marc")
      expect(res.text).toEqual("MARC record")
      expect(aws.getMarc).toHaveBeenCalledWith(
        "6852a770-2961-4836-a833-0b21a9b68041",
        "jdoe",
        "2020-08-20T11:34:40.887Z",
        false
      )
    })
  })

  describe("requesting MARC text", () => {
    it("returns MARC text", async () => {
      const res = await request(app).get(
        "/marc/6852a770-2961-4836-a833-0b21a9b68041/version/jdoe/2020-08-20T11:34:40.887Z"
      )
      expect(res.statusCode).toEqual(200)
      expect(res.type).toEqual("text/plain")
      expect(res.text).toEqual("MARC record")
      expect(aws.getMarc).toHaveBeenCalledWith(
        "6852a770-2961-4836-a833-0b21a9b68041",
        "jdoe",
        "2020-08-20T11:34:40.887Z",
        true
      )
    })
  })
})
