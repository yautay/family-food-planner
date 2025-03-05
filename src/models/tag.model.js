import { DataTypes } from 'sequelize';
import db from '../db/sequelize.js';

const TagModel = db.sequelize.define('Tag', {
  name: {
    type: DataTypes.STRING,
    allowNull: false
  }
});

export default TagModel;
