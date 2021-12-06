/* eslint-disable camelcase */
import {
  GetQueueUrlCommand,
  SendMessageCommand,
  mockSend as mockSqsSend,
} from "@aws-sdk/client-sqs"
import {
  mockCognitoIdentityProviderClient,
  paginateListGroups,
  mockPaginateListGroups,
} from "@aws-sdk/client-cognito-identity-provider"
import {
  InvokeCommand,
  mockSend as mockLambdaSend,
} from "@aws-sdk/client-lambda"
import {
  mockSend as mockS3Send,
  ListObjectsV2Command,
  GetObjectCommand,
} from "@aws-sdk/client-s3"

import {
  requestMarc,
  hasMarc,
  getMarc,
  listGroups,
  buildAndSendSqsMessage,
} from "aws.js"
import { Readable } from "stream"

jest.mock("@aws-sdk/client-cognito-identity-provider", () => {
  const mockCognitoIdentityProviderClient = jest.fn()
  const mockPaginateListGroups = jest.fn()
  return {
    __esModule: true,
    mockCognitoIdentityProviderClient,
    mockPaginateListGroups,
    CognitoIdentityProviderClient: jest
      .fn()
      .mockImplementation(() => mockCognitoIdentityProviderClient),
    paginateListGroups: mockPaginateListGroups,
  }
})

jest.mock("@aws-sdk/client-sqs", () => {
  const mockSend = jest.fn()
  return {
    __esModule: true,
    mockSend,
    GetQueueUrlCommand: jest.fn(),
    SendMessageCommand: jest.fn(),
    SQSClient: jest.fn().mockImplementation(() => {
      return {
        send: mockSend,
      }
    }),
  }
})

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

describe("listGroups", () => {
  describe("getting successful", () => {
    it("resolves record with pagination", async () => {
      mockPaginateListGroups.mockImplementation(() => {
        return [
          {
            Groups: [
              { GroupName: "stanford", Description: "Stanford University" },
              { GroupName: "cornell", Description: "Cornell University" },
            ],
          },
          {
            Groups: [
              { GroupName: "yale", Description: "Yale University" },
              { GroupName: "duke", Description: "Duke University" },
            ],
          },
        ]
      })

      expect(await listGroups()).toEqual([
        { id: "stanford", label: "Stanford University" },
        { id: "cornell", label: "Cornell University" },
        { id: "yale", label: "Yale University" },
        { id: "duke", label: "Duke University" },
      ])
      expect(paginateListGroups).toHaveBeenCalledWith(
        { client: mockCognitoIdentityProviderClient },
        { UserPoolId: "us-west-2_CGd9Wq136", Limit: 60 }
      )
    })
  })

  describe("error", () => {
    it("rejects", async () => {
      mockPaginateListGroups.mockImplementation(() => {
        throw new Error("Get failed")
      })

      await expect(listGroups()).rejects.toThrow("Get failed")
    })
  })
})

describe("buildAndSendSqsMessage", () => {
  it("sends the SQS message to the queue URL returned for the given queue name, with the specified message body", async () => {
    const queueName = "stanford-ils"
    const messageBody = JSON.stringify({ fieldName: "field value" })

    mockSqsSend.mockResolvedValue({
      QueueUrl: "https://sqs.us-west-2.amazonaws.com/0987654321/stanford-ils",
    })

    await buildAndSendSqsMessage(queueName, messageBody)

    expect(GetQueueUrlCommand).toHaveBeenCalledWith({ QueueName: queueName })
    expect(SendMessageCommand).toHaveBeenCalledWith(
      expect.objectContaining({
        QueueUrl: "https://sqs.us-west-2.amazonaws.com/0987654321/stanford-ils",
        MessageBody: messageBody,
      })
    )
    expect(mockSqsSend).toHaveBeenCalledTimes(2)
  })

  it("encounters an error", async () => {
    const errmsg = "you don't have permission to write to this queue :P"

    mockSqsSend.mockRejectedValue(new Error(errmsg))

    await expect(
      buildAndSendSqsMessage(
        "stanford-ils",
        JSON.stringify({ fieldName: "field value" })
      )
    ).rejects.toThrow(errmsg)
  })
})
