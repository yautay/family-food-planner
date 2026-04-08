import { Sequelize } from 'sequelize'
import tagModel from './tag.model.js'
import unitModel from './unit.model.js'
import ingredientModel from './ingredient.model.js'
import userModel from './user.model.js'
import productModel from './product.model.js'
import recipeIngredientModel from './recipe-ingredient.model.js'
import auditLogModel from './audit-log.model.js'
import roleModel from './role.model.js'
import permissionModel from './permission.model.js'
import rolePermissionModel from './role-permission.model.js'
import userRoleModel from './user-role.model.js'
import userPermissionModel from './user-permission.model.js'
import authSessionModel from './auth-session.model.js'
import passwordResetTokenModel from './password-reset-token.model.js'
import packageTypeModel from './package-type.model.js'
import ingredientPackageConversionModel from './ingredient-package-conversion.model.js'

const models = {}

models.tag = tagModel
models.ingredient = ingredientModel
models.unit = unitModel
models.user = userModel
models.product = productModel
models.recipeIngredient = recipeIngredientModel
models.auditLog = auditLogModel
models.role = roleModel
models.permission = permissionModel
models.rolePermission = rolePermissionModel
models.userRole = userRoleModel
models.userPermission = userPermissionModel
models.authSession = authSessionModel
models.passwordResetToken = passwordResetTokenModel
models.packageType = packageTypeModel
models.ingredientPackageConversion = ingredientPackageConversionModel

models.product.belongsTo(models.unit, {
  foreignKey: 'default_unit_id',
  as: 'defaultUnit',
})

models.product.hasMany(models.recipeIngredient, {
  foreignKey: 'product_id',
  as: 'recipeIngredients',
})

models.product.hasMany(models.ingredientPackageConversion, {
  foreignKey: 'product_id',
  as: 'ingredientPackageConversions',
})

models.recipeIngredient.belongsTo(models.product, {
  foreignKey: 'product_id',
  as: 'product',
})

models.recipeIngredient.belongsTo(models.ingredientPackageConversion, {
  foreignKey: 'ingredient_package_conversion_id',
  as: 'ingredientPackageConversion',
})

models.auditLog.belongsTo(models.user, {
  foreignKey: 'actor_user_id',
  as: 'actor',
})

models.user.hasMany(models.authSession, {
  foreignKey: 'user_id',
  as: 'sessions',
})

models.authSession.belongsTo(models.user, {
  foreignKey: 'user_id',
  as: 'user',
})

models.user.hasMany(models.passwordResetToken, {
  foreignKey: 'user_id',
  as: 'passwordResetTokens',
})

models.passwordResetToken.belongsTo(models.user, {
  foreignKey: 'user_id',
  as: 'user',
})

models.ingredientPackageConversion.belongsTo(models.product, {
  foreignKey: 'product_id',
  as: 'product',
})

models.ingredientPackageConversion.belongsTo(models.packageType, {
  foreignKey: 'package_type_id',
  as: 'packageType',
})

models.user.belongsToMany(models.role, {
  through: models.userRole,
  foreignKey: 'user_id',
  otherKey: 'role_id',
  as: 'roles',
})

models.role.belongsToMany(models.user, {
  through: models.userRole,
  foreignKey: 'role_id',
  otherKey: 'user_id',
  as: 'users',
})

models.role.belongsToMany(models.permission, {
  through: models.rolePermission,
  foreignKey: 'role_id',
  otherKey: 'permission_id',
  as: 'permissions',
})

models.permission.belongsToMany(models.role, {
  through: models.rolePermission,
  foreignKey: 'permission_id',
  otherKey: 'role_id',
  as: 'roles',
})

models.user.belongsToMany(models.permission, {
  through: models.userPermission,
  foreignKey: 'user_id',
  otherKey: 'permission_id',
  as: 'directPermissions',
})

models.permission.belongsToMany(models.user, {
  through: models.userPermission,
  foreignKey: 'permission_id',
  otherKey: 'user_id',
  as: 'usersWithDirectPermission',
})

models.userRole.belongsTo(models.role, {
  foreignKey: 'role_id',
  as: 'role',
})

models.userPermission.belongsTo(models.permission, {
  foreignKey: 'permission_id',
  as: 'permission',
})

models.rolePermission.belongsTo(models.permission, {
  foreignKey: 'permission_id',
  as: 'permission',
})

models.Op = Sequelize.Op

export default models
