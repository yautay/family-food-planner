import Sequelize from 'sequelize';
import * as models from '../models/index.js';

const sequelize = new Sequelize({
  dialect: 'sqlite',
  storage: './database.db'
});

const db = {};
db.Sequelize = Sequelize;
db.sequelize = sequelize;

db.tags = models.tag;
db.units = models.unit;
db.ingredient = models.ingredient;

sequelize.sync({ force: true }).then(() => {
  console.log('Database & tables created!');
});

export default db;
