import prompt from 'prompt'
import AuthenticateClient from './authenticateClient.js'

const promptConfig = {
  properties: {
    username: {
      required: true,
      message: 'AWS Cognito username'
    },
    password: {
      required: true,
      message: 'AWS Cognito password',
      hidden: true,
      replace: '*',
    }
  }
}

// Remove noisy 'prompt: ' prefix from username and password prompts
prompt.message = ''
// Do not use colored output -- can cause text not to render on a dark background
prompt.colors = false

// Prompt user for credentials and write Cognito token file
prompt.start()
prompt.get(promptConfig, (err, prompted) => {
  if (err) throw err
  new AuthenticateClient(prompted.username, prompted.password).cognitoTokenToFile()
})
