import fs from "fs"
// For better error message
import util from "util"
import Auth from "@aws-amplify/auth"
import Amplify from "@aws-amplify/core"

export default class AuthenticateClient {
  constructor(username, password) {
    this.username = username
    this.password = password
    this.cognitoTokenFile = ".cognitoToken"

    // Configure Amplify (which supports Cognito / authentication)
    Amplify.default.configure({
      Auth: {
        region: process.env.AWS_REGION || "us-west-2",
        userPoolId: process.env.COGNITO_USER_POOL_ID || "us-west-2_CGd9Wq136",
        userPoolWebClientId:
          process.env.COGNITO_CLIENT_ID || "2u6s7pqkc1grq1qs464fsi82at",
      },
    })
    if (!this.username || !this.password) {
      const errmsg =
        "ERROR: username and password are required (usually passed at command line)"
      console.error(errmsg)
      throw errmsg
    }
  }

  async cognitoTokenToFile() {
    await this.idTokenPromise()
      .then((jwt) => {
        try {
          fs.writeFileSync(this.cognitoTokenFile, jwt)
        } catch (err) {
          console.error(`problem writing to ${this.cognitoTokenFile}: ${err}`)
        }
      })
      .catch((err) => {
        console.error(
          `ERROR: problem getting cognito idToken: ${util.inspect(err)}`
        )
      })
  }

  async idTokenPromise() {
    const cognitoUser = await Auth.default.signIn(this.username, this.password)
    return cognitoUser.signInUserSession.idToken.jwtToken
  }
}
