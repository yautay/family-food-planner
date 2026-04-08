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
import productTagModel from './product-tag.model.js'
import productPackageModel from './product-package.model.js'
import recipeModel from './recipe.model.js'
import recipeNutritionSummaryModel from './recipe-nutrition-summary.model.js'
import dayPlanModel from './day-plan.model.js'
import dayPlanMealModel from './day-plan-meal.model.js'
import mealPlanModel from './meal-plan.model.js'
import mealPlanMealSlotModel from './meal-plan-meal-slot.model.js'
import mealPlanEntryModel from './meal-plan-entry.model.js'
import mealPlanDaySlotModel from './meal-plan-day-slot.model.js'
import mealPlanDaySlotMealModel from './meal-plan-day-slot-meal.model.js'
import shoppingListModel from './shopping-list.model.js'
import shoppingListItemModel from './shopping-list-item.model.js'
import packageModel from './package.model.js'

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
models.productTag = productTagModel
models.productPackage = productPackageModel
models.recipe = recipeModel
models.recipeNutritionSummary = recipeNutritionSummaryModel
models.dayPlan = dayPlanModel
models.dayPlanMeal = dayPlanMealModel
models.mealPlan = mealPlanModel
models.mealPlanMealSlot = mealPlanMealSlotModel
models.mealPlanEntry = mealPlanEntryModel
models.mealPlanDaySlot = mealPlanDaySlotModel
models.mealPlanDaySlotMeal = mealPlanDaySlotMealModel
models.shoppingList = shoppingListModel
models.shoppingListItem = shoppingListItemModel
models.package = packageModel

models.product.belongsTo(models.unit, {
  foreignKey: 'default_unit_id',
  as: 'defaultUnit',
})

models.product.belongsTo(models.packageType, {
  foreignKey: 'default_package_type_id',
  as: 'defaultPackageType',
})

models.product.hasMany(models.recipeIngredient, {
  foreignKey: 'product_id',
  as: 'recipeIngredients',
})

models.recipe.hasMany(models.recipeIngredient, {
  foreignKey: 'recipe_id',
  as: 'ingredients',
})

models.recipe.belongsTo(models.user, {
  foreignKey: 'owner_user_id',
  as: 'owner',
})

models.product.hasMany(models.ingredientPackageConversion, {
  foreignKey: 'product_id',
  as: 'ingredientPackageConversions',
})

models.recipeIngredient.belongsTo(models.product, {
  foreignKey: 'product_id',
  as: 'product',
})

models.recipeIngredient.belongsTo(models.recipe, {
  foreignKey: 'recipe_id',
  as: 'recipe',
})

models.recipeIngredient.belongsTo(models.unit, {
  foreignKey: 'unit_id',
  as: 'unit',
})

models.recipeIngredient.belongsTo(models.package, {
  foreignKey: 'package_id',
  as: 'legacyPackage',
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

models.product.belongsToMany(models.tag, {
  through: models.productTag,
  foreignKey: 'product_id',
  otherKey: 'tag_id',
  as: 'tags',
})

models.tag.belongsToMany(models.product, {
  through: models.productTag,
  foreignKey: 'tag_id',
  otherKey: 'product_id',
  as: 'products',
})

models.productTag.belongsTo(models.product, {
  foreignKey: 'product_id',
  as: 'product',
})

models.productTag.belongsTo(models.tag, {
  foreignKey: 'tag_id',
  as: 'tag',
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

models.dayPlan.belongsTo(models.user, {
  foreignKey: 'owner_user_id',
  as: 'owner',
})

models.dayPlan.hasMany(models.dayPlanMeal, {
  foreignKey: 'day_plan_id',
  as: 'meals',
})

models.dayPlanMeal.belongsTo(models.dayPlan, {
  foreignKey: 'day_plan_id',
  as: 'dayPlan',
})

models.dayPlanMeal.belongsTo(models.recipe, {
  foreignKey: 'recipe_id',
  as: 'recipe',
})

models.mealPlan.belongsTo(models.user, {
  foreignKey: 'owner_user_id',
  as: 'owner',
})

models.mealPlan.hasMany(models.mealPlanEntry, {
  foreignKey: 'meal_plan_id',
  as: 'entries',
})

models.mealPlan.hasMany(models.mealPlanMealSlot, {
  foreignKey: 'meal_plan_id',
  as: 'mealSlots',
})

models.mealPlanMealSlot.belongsTo(models.mealPlan, {
  foreignKey: 'meal_plan_id',
  as: 'mealPlan',
})

models.mealPlanEntry.belongsTo(models.mealPlan, {
  foreignKey: 'meal_plan_id',
  as: 'mealPlan',
})

models.mealPlanEntry.belongsTo(models.recipe, {
  foreignKey: 'recipe_id',
  as: 'recipe',
})

models.mealPlan.hasMany(models.mealPlanDaySlot, {
  foreignKey: 'meal_plan_id',
  as: 'daySlots',
})

models.mealPlanDaySlot.belongsTo(models.mealPlan, {
  foreignKey: 'meal_plan_id',
  as: 'mealPlan',
})

models.mealPlanDaySlot.belongsTo(models.dayPlan, {
  foreignKey: 'day_plan_id',
  as: 'dayPlan',
})

models.mealPlanDaySlot.hasMany(models.mealPlanDaySlotMeal, {
  foreignKey: 'day_slot_id',
  as: 'meals',
})

models.mealPlanDaySlotMeal.belongsTo(models.mealPlanDaySlot, {
  foreignKey: 'day_slot_id',
  as: 'daySlot',
})

models.mealPlanDaySlotMeal.belongsTo(models.recipe, {
  foreignKey: 'recipe_id',
  as: 'recipe',
})

models.shoppingList.belongsTo(models.user, {
  foreignKey: 'owner_user_id',
  as: 'owner',
})

models.shoppingList.belongsTo(models.mealPlan, {
  foreignKey: 'meal_plan_id',
  as: 'mealPlan',
})

models.shoppingList.hasMany(models.shoppingListItem, {
  foreignKey: 'shopping_list_id',
  as: 'items',
})

models.shoppingListItem.belongsTo(models.shoppingList, {
  foreignKey: 'shopping_list_id',
  as: 'shoppingList',
})

models.shoppingListItem.belongsTo(models.product, {
  foreignKey: 'product_id',
  as: 'product',
})

models.shoppingListItem.belongsTo(models.unit, {
  foreignKey: 'unit_id',
  as: 'unit',
})

models.package.belongsTo(models.unit, {
  foreignKey: 'unit_id',
  as: 'unit',
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
