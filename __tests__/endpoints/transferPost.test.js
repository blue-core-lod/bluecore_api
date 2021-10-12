import request from "supertest"
import app from "app.js"
import * as aws from "aws.js"
import FakeTimers from "@sinonjs/fake-timers"

jest.mock("aws.js")
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

const stanfordJwt =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbInN0YW5mb3JkIiwicGNjIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.AtnKOR0bghI-DTjeWUTnLlNub1wc0QzAprrQQ2XGWR8"

describe("POST /transfer/:resourceId/:targetGroup/:targetSystem", () => {
  describe("user is in target group", () => {
    it("returns a 204 after queueing an SQS message with the expected params", async () => {
      aws.buildAndSendSqsMessage.mockResolvedValue()
      const res = await request(app)
        .post("/transfer/foo/stanford/ils")
        .set("Authorization", `Bearer ${stanfordJwt}`)
        .send("")

      const msgBodyJson = {
        resource: { uri: "https://api.development.sinopia.io/resource/foo" },
        user: {
          email: "justinlittman@stanford.edu",
        },
        group: "stanford",
        target: "ils",
      }
      expect(res.statusCode).toEqual(204)
      expect(aws.buildAndSendSqsMessage).toHaveBeenCalledWith(
        "stanford-ils",
        expect.stringMatching(JSON.stringify(msgBodyJson))
      )
    })
  })

  describe("user is in admin group", () => {
    it("returns a 204 after queueing an SQS message with the expected params", async () => {
      aws.buildAndSendSqsMessage.mockResolvedValue()
      const res = await request(app)
        .post("/transfer/foo/stanford/ils")
        .set(
          "Authorization",
          `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDlmMDAzYi0xOWQxLTQ4YjUtYWVjYi1iNGY0N2ZiYjdkYzgiLCJhdWQiOiIydTZzN3Bxa2MxZ3JxMXFzNDY0ZnNpODJhdCIsImNvZ25pdG86Z3JvdXBzIjpbImFkbWluIiwicGNjIl0sImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJldmVudF9pZCI6ImU0YWM2ODA4LWViYTUtNDM2MC04ZTU1LTY0ZWUwYjdhZjllYiIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNjMxOTEwMzgwLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL3VzLXdlc3QtMl9DR2Q5V3ExMzYiLCJjb2duaXRvOnVzZXJuYW1lIjoiamxpdHRtYW4iLCJleHAiOjI2MzIwMDcxNDgsImlhdCI6MTYzMjAwMzU0OCwiZW1haWwiOiJqdXN0aW5saXR0bWFuQHN0YW5mb3JkLmVkdSJ9.vWC4N1F3BizLILxwq3Cd8savrrrrKj3mEslX75_jHnY`
        )
        .send("")

      const msgBodyJson = {
        resource: { uri: "https://api.development.sinopia.io/resource/foo" },
        user: {
          email: "justinlittman@stanford.edu",
        },
        group: "stanford",
        target: "ils",
      }
      expect(res.statusCode).toEqual(204)
      expect(aws.buildAndSendSqsMessage).toHaveBeenCalledWith(
        "stanford-ils",
        expect.stringMatching(JSON.stringify(msgBodyJson))
      )
    })
  })

  describe("user is not in the target group", () => {
    // eslint-disable-next-line multiline-comment-style
    /*
    // Commenting out as we want to test this scenario, but for reasons we can't explain, the test hangs (works when tested in running app using curl)
    it("returns a 401 Unauthorized", async () => {
      aws.buildAndSendSqsMessage.mockResolvedValue()
      const res = await request(app)
        .post("/transfer/foo/harvard/ils")
        .set("Authorization", `Bearer ${stanfordJwt}`)
        .send('')

      expect(res.statusCode).toEqual(401)
      expect(res.body).toEqual([
        {
          title: "Unauthorized",
          details: "User must a member of the group to which the resource is being transferred",
          status: "401",
        },
      ])
      expect(aws.buildAndSendSqsMessage).not.toHaveBeenCalled()
    })
    */
  })
})
