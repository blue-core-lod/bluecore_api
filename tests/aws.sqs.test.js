/* eslint-disable camelcase */
import {
  GetQueueUrlCommand,
  SendMessageCommand,
  mockSend as mockSqsSend,
} from "@aws-sdk/client-sqs"
import { buildAndSendSqsMessage } from "aws.js"

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
