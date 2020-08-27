import jwksRsa from 'jwks-rsa'

const cognitoUserPoolId = process.env.COGNITO_USER_POOL_ID || 'us-west-2_CGd9Wq136'
const awsRegion = process.env.AWS_REGION || 'us-west-2'

// JWT
const publicKeySecret = jwksRsa.expressJwtSecret({
    cache: true,
    rateLimit: true,
    jwksUri: `https://cognito-idp.${awsRegion}.amazonaws.com/${cognitoUserPoolId}/.well-known/jwks.json`
  })

const jwtConfig = () => ({ secret: publicKeySecret, algorithms: ['RS256'] })

export default jwtConfig
