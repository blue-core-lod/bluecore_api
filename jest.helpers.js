process.env.API_BASE_URL = "https://api.development.sinopia.io"

const mockConnect = (mockDb) => {
  return (req, res, next) => {
    req.db = mockDb
    next()
  }
}
global.mockConnect = mockConnect
