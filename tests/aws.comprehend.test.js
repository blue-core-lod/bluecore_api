/* eslint-disable camelcase */
import {
  mockSend as mockComprehendSend,
  DetectDominantLanguageCommand,
} from "@aws-sdk/client-comprehend"
import { detectLanguage } from "aws.js"

jest.mock("@aws-sdk/client-comprehend", () => {
  const mockSend = jest.fn()
  return {
    __esModule: true,
    mockSend,
    ComprehendClient: jest.fn().mockImplementation(() => {
      return {
        send: mockSend,
      }
    }),
    DetectDominantLanguageCommand: jest.fn(),
  }
})

describe("detectLanguage", () => {
  describe("successful", () => {
    it("invokes comprehend and resolves", async () => {
      mockComprehendSend.mockResolvedValue({
        Languages: [
          { LanguageCode: "es", Score: 0.23285673558712006 },
          { LanguageCode: "en", Score: 0.4512737989425659 },
        ],
      })

      expect(await detectLanguage("el diablo")).toEqual([
        { language: "en", score: 0.4512737989425659 },
        { language: "es", score: 0.23285673558712006 },
      ])
      expect(DetectDominantLanguageCommand).toHaveBeenCalledWith({
        Text: "el diablo",
      })
      expect(mockComprehendSend).toHaveBeenCalledTimes(1)
    })
  })

  describe("failure", () => {
    it("invokes comprehend and rejects", async () => {
      mockComprehendSend.mockRejectedValue(new Error("AWS fail"))

      await expect(detectLanguage("el diablo")).rejects.toThrow("AWS fail")
    })
  })
})
