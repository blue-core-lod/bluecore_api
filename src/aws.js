/* eslint-disable camelcase */
import {
  CognitoIdentityProviderClient,
  paginateListGroups,
} from "@aws-sdk/client-cognito-identity-provider"
import {
  SQSClient,
  GetQueueUrlCommand,
  SendMessageCommand,
} from "@aws-sdk/client-sqs"
import {
  S3Client,
  ListObjectsV2Command,
  GetObjectCommand,
} from "@aws-sdk/client-s3"
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda"
import {
  ComprehendClient,
  DetectDominantLanguageCommand,
} from "@aws-sdk/client-comprehend"
import getStream from "get-stream"
import _ from "lodash"

const config = {
  region: process.env.AWS_REGION || "us-west-2",
}

const cognitoIdentityProviderClient = new CognitoIdentityProviderClient(config)
const sqsClient = new SQSClient(config)
const s3Client = new S3Client(config)
const lambdaClient = new LambdaClient(config)
const comprehendClient = new ComprehendClient(config)

const bucketName = process.env.AWS_BUCKET || "sinopia-marc-development"
const lambdaName =
  process.env.AWS_RDF2MARC_LAMBDA || "sinopia-rdf2marc-development"
const userPoolId = process.env.COGNITO_USER_POOL_ID || "us-west-2_CGd9Wq136"

export const requestMarc = async (
  resourceUri,
  resourceId,
  username,
  timestamp
) => {
  // These are tied to the user so that can list all of the MARC records requested by a user.
  const marcKey = `${username}/${resourceId}/${timestamp}`
  const marcPath = `${marcKey}/record.mar`
  const marcTxtPath = `${marcKey}/record.txt`
  const errorPath = `${marcKey}/error.txt`
  // Invoke lambda.
  const params = {
    FunctionName: lambdaName,
    Payload: JSON.stringify({
      instance_uri: resourceUri,
      marc_path: marcPath,
      marc_txt_path: marcTxtPath,
      error_path: errorPath,
      bucket: bucketName,
    }),
    InvocationType: "Event",
  }
  await lambdaClient.send(new InvokeCommand(params))
}

export const hasMarc = async (resourceId, username, timestamp) => {
  const params = {
    Bucket: bucketName,
    Prefix: `marc/${username}/${resourceId}/${timestamp}`,
  }
  const listResp = await s3Client.send(new ListObjectsV2Command(params))
  if (listResp.Contents?.find((content) => content.Key.endsWith("error.txt"))) {
    const errorTxt = await getError(resourceId, username, timestamp)
    throw new Error(errorTxt)
  } else if (
    listResp.Contents?.find((content) => content.Key.endsWith("record.mar"))
  ) {
    return true
  }
  return false
}

export const getMarc = async (resourceId, username, timestamp, asText) => {
  const fileExt = asText ? ".txt" : ".mar"
  const params = {
    Bucket: bucketName,
    Key: `marc/${username}/${resourceId}/${timestamp}/record${fileExt}`,
  }
  const getResp = await s3Client.send(new GetObjectCommand(params))
  return getStream(getResp.Body)
}

const getError = async (resourceId, username, timestamp) => {
  const params = {
    Bucket: bucketName,
    Key: `marc/${username}/${resourceId}/${timestamp}/error.txt`,
  }
  const getResp = await s3Client.send(new GetObjectCommand(params))
  return getStream(getResp.Body)
}

export const listGroups = async () => {
  let groups = []

  for await (const page of paginateListGroups(
    { client: cognitoIdentityProviderClient },
    { UserPoolId: userPoolId, Limit: 60 }
  )) {
    groups = [...groups, ...page.Groups]
  }

  return groups.map((group) => ({
    id: group.GroupName,
    label: group.Description || group.GroupName,
  }))
}

export const buildAndSendSqsMessage = async (queueName, messageBody) => {
  const messageParams = await buildSqsMessageParams(queueName, messageBody)
  await sqsClient.send(new SendMessageCommand(messageParams))
}

const buildSqsMessageParams = async (queueName, messageBody) => {
  const queueUrlresp = await sqsClient.send(
    new GetQueueUrlCommand({ QueueName: queueName })
  )
  return {
    QueueUrl: queueUrlresp.QueueUrl,
    MessageBody: messageBody,
    MessageAttributes: {
      timestamp: {
        DataType: "String",
        StringValue: new Date().toISOString(),
      },
    },
  }
}

export const detectLanguage = async (text) => {
  const detectResp = await comprehendClient.send(
    new DetectDominantLanguageCommand({ Text: text })
  )
  const languages = detectResp.Languages.map((languageResp) => {
    return {
      language: languageResp.LanguageCode,
      score: languageResp.Score,
    }
  })
  return _.sortBy(languages, ["score"]).reverse()
}
