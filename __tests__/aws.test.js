/* eslint-disable camelcase */
import { requestMarc, hasMarc, getMarc, listGroups } from "aws.js"

const mockInvokeAsync = jest.fn()
const mockListObjects = jest.fn()
const mockGetObject = jest.fn()
const mockListGroups = jest.fn()
jest.mock("aws-sdk", () => {
  return {
    config: { update: jest.fn() },
    Lambda: jest.fn(() => ({
      invokeAsync: mockInvokeAsync,
    })),
    S3: jest.fn(() => ({
      listObjectsV2: mockListObjects,
      getObject: mockGetObject,
    })),
    CognitoIdentityServiceProvider: jest.fn(() => ({
      listGroups: mockListGroups,
    })),
  }
})

describe("requestMarc", () => {
  describe("successful", () => {
    it("invokes lambda and resolves", async () => {
      mockInvokeAsync.mockImplementation((params, callback) => {
        expect(params).toEqual({
          FunctionName: "sinopia-rdf2marc-development",
          InvokeArgs: JSON.stringify({
            instance_uri:
              "https://api.development.sinopia.io/resource/6852a770-2961-4836-a833-0b21a9b68041",
            marc_path:
              "jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/record.mar",
            marc_txt_path:
              "jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/record.txt",
            error_path:
              "jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/error.txt",
            bucket: "sinopia-marc-development",
          }),
        })
        callback(null, true)
      })

      expect(
        await requestMarc(
          "https://api.development.sinopia.io/resource/6852a770-2961-4836-a833-0b21a9b68041",
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).toEqual()
    })
  })

  describe("failure", () => {
    it("invokes lambda and rejects", async () => {
      mockInvokeAsync.mockImplementation((params, callback) => {
        callback(new Error("AWS fail"), null)
      })
      await expect(
        requestMarc(
          "https://api.development.sinopia.io/resource/6852a770-2961-4836-a833-0b21a9b68041",
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).rejects.toThrow("AWS fail")
    })
  })
})

describe("hasMarc", () => {
  describe("finds MARC record", () => {
    it("resolves true", async () => {
      mockListObjects.mockImplementation((params, callback) => {
        expect(params).toEqual({
          Bucket: "sinopia-marc-development",
          Prefix:
            "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z",
        })
        callback(null, {
          Contents: [
            {
              Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/record.mar",
            },
          ],
        })
      })
      expect(
        await hasMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).toBe(true)
    })
  })

  describe("finds error file", () => {
    it("retrieves error file and rejects", async () => {
      mockListObjects.mockImplementation((params, callback) => {
        callback(null, {
          Contents: [
            {
              Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/error.txt",
            },
          ],
        })
      })
      mockGetObject.mockImplementation((params, callback) => {
        expect(params).toEqual({
          Bucket: "sinopia-marc-development",
          Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/error.txt",
        })
        callback(null, {
          Body: { toString: jest.fn().mockReturnValue("Bad record") },
        })
      })
      await expect(
        hasMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).rejects.toThrow("Bad record")
    })
  })

  describe("finds no files", () => {
    it("resolves false", async () => {
      mockListObjects.mockImplementation((params, callback) => {
        callback(null, { Contents: [] })
      })
      expect(
        await hasMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).toBe(false)
    })
  })
})

describe("getMarc", () => {
  describe("getting MARC record", () => {
    it("resolves record", async () => {
      mockGetObject.mockImplementation((params, callback) => {
        expect(params).toEqual({
          Bucket: "sinopia-marc-development",
          Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/record.mar",
        })
        callback(null, { Body: "The record" })
      })
      expect(
        await getMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).toBe("The record")
    })
  })

  describe("getting MARC text", () => {
    it("resolves text", async () => {
      mockGetObject.mockImplementation((params, callback) => {
        expect(params).toEqual({
          Bucket: "sinopia-marc-development",
          Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/record.txt",
        })
        callback(null, { Body: "The record" })
      })
      expect(
        await getMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z",
          true
        )
      ).toBe("The record")
    })
  })

  describe("error", () => {
    it("rejects", async () => {
      mockGetObject.mockImplementation((params, callback) => {
        callback(new Error("Get failed"), null)
      })
      await expect(
        getMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).rejects.toThrow("Get failed")
    })
  })
})

describe("listGroups", () => {
  describe("getting successful", () => {
    it("resolves record", async () => {
      mockListGroups.mockImplementation((params, callback) => {
        expect(params).toEqual({
          UserPoolId: "us-west-2_CGd9Wq136",
          Limit: 60,
        })
        callback(null, {
          Groups: [
            { GroupName: "stanford", Description: "Stanford University" },
            { GroupName: "cornell", Description: "Cornell University" },
          ],
        })
      })
      expect(await listGroups()).toEqual([
        { id: "stanford", label: "Stanford University" },
        { id: "cornell", label: "Cornell University" },
      ])
    })
  })

  describe("error", () => {
    it("rejects", async () => {
      mockListGroups.mockImplementation((params, callback) => {
        callback(new Error("Get failed"), null)
      })
      await expect(listGroups()).rejects.toThrow("Get failed")
    })
  })
})
