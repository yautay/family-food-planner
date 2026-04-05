import Database from 'better-sqlite3'

const catalogDb = new Database('./database.db')
catalogDb.pragma('foreign_keys = ON')

export default catalogDb
