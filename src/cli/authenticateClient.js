import fs from "fs"
// For better error message
import util from "util"
import NodeFetch from "node-fetch"
import cognitoPkg from "amazon-cognito-identity-js"
const { AuthenticationDetails, CognitoUser, CognitoUserPool } = cognitoPkg
import awsSdkPkg from "aws-sdk"
const { SharedIniFileCredentials, CognitoIdentityServiceProvider, Config } =
  awsSdkPkg

// Need fetch polyfill because amazon-cognito-identity-js uses the Fetch API.
// See: https://github.com/aws-amplify/amplify-js/tree/master/packages/amazon-cognito-identity-js#setup
global.fetch = NodeFetch

export default class AuthenticateClient {
  constructor(username, password) {
    this.username = username
    this.password = password
    // Extracting these to methods makes for easier testing
    this.userPoolId = process.env.COGNITO_USER_POOL_ID || "us-west-2_CGd9Wq136"
    this.appClientId =
      process.env.COGNITO_CLIENT_ID || "2u6s7pqkc1grq1qs464fsi82at"
    this.cognitoTokenFile = ".cognitoToken"
    this.awsRegion = process.env.AWS_REGION || "us-west-2"
    this.cognitoIss =
      process.env.AWS_COGNITO_ENDPOINT ||
      `https://cognito-idp.${this.awsRegion}.amazonaws.com/${this.userPoolId}`

    if (!this.username || !this.password) {
      const errmsg =
        "ERROR: username and password are required (usually passed at command line)"
      console.error(errmsg)
      throw errmsg
    }
  }

  async cognitoTokenToFile() {
    await this.accessTokenPromise()
      .then((jwt) => {
        try {
          fs.writeFileSync(this.cognitoTokenFile, jwt)
        } catch (err) {
          console.error(`problem writing to ${this.cognitoTokenFile}: ${err}`)
        }
      })
      .catch((err) => {
        console.error(
          `ERROR: problem getting cognito accessToken: ${util.inspect(err)}`
        )
      })
  }

  async webId(cognitoUserName) {
    try {
      const userSub = await this.userSubFromCognitoPool(cognitoUserName)
      return `${this.cognitoIss}/${userSub}`
    } catch (err) {
      const errmsg = `ERROR: problem getting webid for ${cognitoUserName}: ${util.inspect(
        err
      )}`
      console.error(errmsg)
      throw errmsg
    }
  }

  userSubFromCognitoPool(cognitoUserName) {
    const awsProfile = process.env.AWS_PROFILE || ""
    if (awsProfile) {
      // Loads credential info from .aws/config as well as .aws/credentials
      process.env.AWS_SDK_LOAD_CONFIG = true
      const credentials = new SharedIniFileCredentials({ profile: awsProfile })
      Config.credentials = credentials
    }
    // Else env vars AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY are sufficient (e.g. circleci, AWS containers)

    const cognito = new CognitoIdentityServiceProvider({
      // This value pertains something inside the AWS SDK npm package itself
      apiVersion: "2016-04-18",
      region: this.awsRegion,
    })

    const desiredUserParams = {
      UserPoolId: this.userPoolId,
      Username: cognitoUserName,
    }

    return cognito
      .adminGetUser(desiredUserParams)
      .promise()
      .then((data, err) => {
        const sub = this.userSubFromUserData(data, err)
        return sub
      })
  }

  static userSubFromUserData(userData, err) {
    if (err) {
      const errmsg = `ERROR: problem retrieving sub user attribute: ${util.inspect(
        err
      )}`
      console.error(errmsg)
      throw errmsg
    }
    const subAttribute = userData.UserAttributes.find((element) => {
      // Each element is an object:
      // { Name: 'sub', Value: '789dda7d-25c0-4a8f-9c62-b3116a97cc9b' }
      return element.Name === "sub"
    })
    return subAttribute.Value
  }

  accessTokenPromise() {
    return new Promise((resolve, reject) => {
      this.cognitoUser().authenticateUser(this.authenticationDetails(), {
        onSuccess: (result) => {
          const jwt = result.getAccessToken().getJwtToken()
          if (jwt) resolve(jwt)
          else
            reject(
              new Error(
                `ERROR: retrieved null cognito access token for ${this.username}`
              )
            )
        },
        onFailure: (err) => {
          reject(err)
        },
      })
    })
  }

  authenticationDetails() {
    const authenticationData = {
      Username: this.username,
      Password: this.password,
    }
    return new AuthenticationDetails(authenticationData)
  }

  cognitoUser() {
    const poolData = {
      UserPoolId: this.userPoolId,
      ClientId: this.appClientId,
    }
    const userPool = new CognitoUserPool(poolData)
    const userData = {
      Username: this.username,
      Pool: userPool,
    }
    return new CognitoUser(userData)
  }
}
