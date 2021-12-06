/* eslint-disable camelcase */
import {
  InvokeCommand,
  mockSend as mockLambdaSend,
} from "@aws-sdk/client-lambda"
import {
  mockSend as mockS3Send,
  ListObjectsV2Command,
  GetObjectCommand,
} from "@aws-sdk/client-s3"
import { requestMarc, hasMarc, getMarc } from "aws.js"
import { Readable } from "stream"

jest.mock("@aws-sdk/client-s3", () => {
  const mockSend = jest.fn()
  return {
    __esModule: true,
    mockSend,
    ListObjectsV2Command: jest.fn(),
    GetObjectCommand: jest.fn(),
    S3Client: jest.fn().mockImplementation(() => {
      return {
        send: mockSend,
      }
    }),
  }
})

jest.mock("@aws-sdk/client-lambda", () => {
  const mockSend = jest.fn()
  return {
    __esModule: true,
    mockSend,
    LambdaClient: jest.fn().mockImplementation(() => {
      return {
        send: mockSend,
      }
    }),
    InvokeCommand: jest.fn(),
  }
})

describe("requestMarc", () => {
  describe("successful", () => {
    it("invokes lambda and resolves", async () => {
      await requestMarc(
        "https://api.development.sinopia.io/resource/6852a770-2961-4836-a833-0b21a9b68041",
        "6852a770-2961-4836-a833-0b21a9b68041",
        "jdoe",
        "2020-08-20T11:34:40.887Z"
      )
      expect(InvokeCommand).toHaveBeenCalledWith({
        FunctionName: "sinopia-rdf2marc-development",
        Payload: JSON.stringify({
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
        InvocationType: "Event",
      })
      expect(mockLambdaSend).toHaveBeenCalledTimes(1)
    })
  })

  describe("failure", () => {
    it("invokes lambda and rejects", async () => {
      mockLambdaSend.mockRejectedValue(new Error("AWS fail"))

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
      mockS3Send.mockResolvedValue({
        Contents: [
          {
            Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/record.mar",
          },
        ],
      })
      expect(
        await hasMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).toBe(true)
      expect(ListObjectsV2Command).toHaveBeenCalledWith({
        Bucket: "sinopia-marc-development",
        Prefix:
          "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z",
      })
      expect(mockS3Send).toHaveBeenCalledTimes(1)
    })
  })

  describe("finds error file", () => {
    it("retrieves error file and rejects", async () => {
      mockS3Send
        .mockResolvedValue({
          Body: Readable.from("Bad record"),
        })
        .mockResolvedValueOnce({
          Contents: [
            {
              Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/error.txt",
            },
          ],
        })
      await expect(
        hasMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).rejects.toThrow("Bad record")
      expect(GetObjectCommand).toHaveBeenCalledWith({
        Bucket: "sinopia-marc-development",
        Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/error.txt",
      })
      expect(mockS3Send).toHaveBeenCalledTimes(2)
    })
  })

  describe("finds no files", () => {
    it("resolves false", async () => {
      mockS3Send.mockResolvedValue({
        Contents: [],
      })
      expect(
        await hasMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).toBe(false)
      expect(mockS3Send).toHaveBeenCalledTimes(1)
    })
  })
})

describe("getMarc", () => {
  describe("getting MARC record", () => {
    it("resolves record", async () => {
      mockS3Send.mockResolvedValue({
        Body: Readable.from("The record"),
      })
      expect(
        await getMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z"
        )
      ).toBe("The record")
      expect(GetObjectCommand).toHaveBeenCalledWith({
        Bucket: "sinopia-marc-development",
        Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/record.mar",
      })
      expect(mockS3Send).toHaveBeenCalledTimes(1)
    })
  })

  describe("getting MARC text", () => {
    it("resolves text", async () => {
      mockS3Send.mockResolvedValue({
        Body: Readable.from("The record"),
      })
      expect(
        await getMarc(
          "6852a770-2961-4836-a833-0b21a9b68041",
          "jdoe",
          "2020-08-20T11:34:40.887Z",
          true
        )
      ).toBe("The record")
      expect(GetObjectCommand).toHaveBeenCalledWith({
        Bucket: "sinopia-marc-development",
        Key: "marc/jdoe/6852a770-2961-4836-a833-0b21a9b68041/2020-08-20T11:34:40.887Z/record.txt",
      })
      expect(mockS3Send).toHaveBeenCalledTimes(1)
    })
  })

  describe("error", () => {
    it("rejects", async () => {
      mockS3Send.mockRejectedValue(new Error("Get failed"))
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
