<?php
/**
 * Plugin Name: Auto Permanent Link
 * Description: 記事タイトルから AI で英語スラッグ（パーマリンク）を推奨する。投稿画面のボタンでオンデマンド実行。
 * Version:     1.0.0
 * Author:      Tomotaka Kizawa
 * License:     GPL-2.0-or-later
 * Text Domain: auto-permanent-link
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'APL_VERSION', '1.0.0' );
define( 'APL_PLUGIN_FILE', __FILE__ );
define( 'APL_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'APL_PLUGIN_URL', plugin_dir_url( __FILE__ ) );

// 設定のオプションキー
define( 'APL_OPT_ENDPOINT', 'apl_api_endpoint' );   // 例: https://xxxx.execute-api.ap-northeast-1.amazonaws.com/prod
define( 'APL_OPT_SHARED_SECRET', 'apl_shared_secret' ); // (A) X-Api-Secret に送る値
define( 'APL_OPT_API_KEY', 'apl_api_key' );         // (B) x-api-key に送る値

require_once APL_PLUGIN_DIR . 'includes/class-apl-settings.php';
require_once APL_PLUGIN_DIR . 'includes/class-apl-metabox.php';
require_once APL_PLUGIN_DIR . 'includes/class-apl-rest.php';
require_once APL_PLUGIN_DIR . 'includes/class-apl-save.php';

add_action(
	'plugins_loaded',
	function () {
		APL_Settings::instance();
		APL_Metabox::instance();
		APL_Rest::instance();
		APL_Save::instance();
	}
);
