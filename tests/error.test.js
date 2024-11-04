import request from "supertest"
import app from "app.js"
import connect from "mongo.js"
import Honeybadger from "@honeybadger-io/js"

// Configure bogus HB key for tests only
Honeybadger.configure({
  apiKey: "bogus",
})

jest.mock("mongo.js")
jest.mock("@honeybadger-io/js")

describe("500 Server error", () => {
  const error = new Error("Ooops")
  const url = "/user/nchomsky"

  it("returns server error and notifies HB", async () => {
    connect.mockImplementation(() => {
      throw error
    })
    const res = await request(app).get(url).send()
    expect(Honeybadger.notify).toHaveBeenCalledTimes(1)
    expect(Honeybadger.notify).toHaveBeenCalledWith(error, {
      context: {
        method: "GET",
        url,
      },
    })
    expect(res.statusCode).toEqual(500)
    expect(res.body).toEqual([
      { details: "Ooops", status: "500", title: "Server error" },
    ])
  })
})

describe("404 Server error", () => {
  it("returns server error and does not notify HB", async () => {
    connect.mockImplementation(() => {
      const err = new Error("Not Found")
      err.status = 404
      throw err
    })
    const res = await request(app).get("/user/nchomsky").send()
    expect(Honeybadger.notify).toHaveBeenCalledTimes(0)
    expect(res.statusCode).toEqual(404)
    expect(res.body).toEqual([
      { details: "Not Found", status: "404", title: "Not Found" },
    ])
  })
})
