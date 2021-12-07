/* eslint-disable camelcase */
import {
  mockCognitoIdentityProviderClient,
  paginateListGroups,
  mockPaginateListGroups,
} from "@aws-sdk/client-cognito-identity-provider"
import { listGroups } from "aws.js"

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
