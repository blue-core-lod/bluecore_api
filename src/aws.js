/* eslint-disable camelcase */
import AWS from "aws-sdk"

AWS.config.update({
  accessKeyId: process.env.AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  region: process.env.AWS_REGION || "us-west-2",
  apiVersions: {
    lambda: "2015-03-31",
    s3: "2006-03-01",
    cognitoidentityserviceprovider: "2016-04-18",
  },
})

const bucketName = process.env.AWS_BUCKET || "sinopia-marc-development"
const lambdaName =
  process.env.AWS_RDF2MARC_LAMBDA || "sinopia-rdf2marc-development"
const userPoolId = process.env.COGNITO_USER_POOL_ID || "us-west-2_CGd9Wq136"

export const requestMarc = (resourceUri, resourceId, username, timestamp) => {
  // These are tied to the user so that can list all of the MARC records requested by a user.
  const marcKey = `${username}/${resourceId}/${timestamp}`
  const marcPath = `${marcKey}/record.mar`
  const marcTxtPath = `${marcKey}/record.txt`
  const errorPath = `${marcKey}/error.txt`
  // Invoke lambda.
  const params = {
    FunctionName: lambdaName,
    InvokeArgs: JSON.stringify({
      instance_uri: resourceUri,
      marc_path: marcPath,
      marc_txt_path: marcTxtPath,
      error_path: errorPath,
      bucket: bucketName,
    }),
  }
  const lambda = new AWS.Lambda()
  return new Promise((resolve, reject) => {
    lambda.invokeAsync(params, (err) => {
      if (err) reject(err)
      else resolve()
    })
  })
}

export const hasMarc = (resourceId, username, timestamp) => {
  const params = {
    Bucket: bucketName,
    Prefix: `marc/${username}/${resourceId}/${timestamp}`,
  }
  const s3 = new AWS.S3()
  return new Promise((resolve, reject) => {
    s3.listObjectsV2(params, (err, data) => {
      if (err) reject(err)
      else if (
        data.Contents.find((content) => content.Key.endsWith("error.txt"))
      ) {
        return getError(resourceId, username, timestamp)
          .then((errorTxt) => reject(new Error(errorTxt)))
          .catch((err) => reject(err))
      } else if (
        data.Contents.find((content) => content.Key.endsWith("record.mar"))
      ) {
        resolve(true)
      } else resolve(false)
    })
  })
}

export const getMarc = (resourceId, username, timestamp, asText) => {
  const fileExt = asText ? ".txt" : ".mar"
  const params = {
    Bucket: bucketName,
    Key: `marc/${username}/${resourceId}/${timestamp}/record${fileExt}`,
  }
  const s3 = new AWS.S3()
  return new Promise((resolve, reject) => {
    s3.getObject(params, (err, data) => {
      if (err) reject(err)
      else resolve(data.Body)
    })
  })
}

const getError = (resourceId, username, timestamp) => {
  const params = {
    Bucket: bucketName,
    Key: `marc/${username}/${resourceId}/${timestamp}/error.txt`,
  }
  const s3 = new AWS.S3()
  return new Promise((resolve, reject) => {
    s3.getObject(params, (err, data) => {
      if (err) reject(err)
      else resolve(data.Body.toString("utf-8"))
    })
  })
}

export const listGroups = () => {
  const cognito = new AWS.CognitoIdentityServiceProvider()
  return new Promise((resolve, reject) => {
    cognito.listGroups({ UserPoolId: userPoolId, Limit: 60 }, (err, data) => {
      if (err) reject(err)
      else
        resolve(
          data.Groups.map((group) => ({
            id: group.GroupName,
            label: group.Description || group.GroupName,
          }))
        )
    })
  })
}
