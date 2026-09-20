<?php
/**
 * 設定ページ: Lambda エンドポイント URL、共有シークレット(A)、APIキー(B) を保持する。
 * 設定 → Auto Permanent Link に表示。manage_options 権限が必要。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class APL_Settings {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'admin_menu', array( $this, 'add_menu' ) );
		add_action( 'admin_init', array( $this, 'register' ) );
	}

	public function add_menu() {
		add_options_page(
			'Auto Permanent Link',
			'Auto Permanent Link',
			'manage_options',
			'auto-permanent-link',
			array( $this, 'render_page' )
		);
	}

	public function register() {
		register_setting( 'apl_settings', APL_OPT_ENDPOINT, array( 'sanitize_callback' => 'esc_url_raw' ) );
		register_setting( 'apl_settings', APL_OPT_SHARED_SECRET, array( 'sanitize_callback' => 'sanitize_text_field' ) );
		register_setting( 'apl_settings', APL_OPT_API_KEY, array( 'sanitize_callback' => 'sanitize_text_field' ) );
	}

	public function render_page() {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}
		$endpoint = esc_attr( get_option( APL_OPT_ENDPOINT, '' ) );
		$secret   = esc_attr( get_option( APL_OPT_SHARED_SECRET, '' ) );
		$api_key  = esc_attr( get_option( APL_OPT_API_KEY, '' ) );
		?>
		<div class="wrap">
			<h1>Auto Permanent Link 設定</h1>
			<p>記事タイトルから英語スラッグを推奨する AI バックエンド(API Gateway + Lambda)への接続設定です。</p>
			<form method="post" action="options.php">
				<?php settings_fields( 'apl_settings' ); ?>
				<table class="form-table" role="presentation">
					<tr>
						<th scope="row"><label for="apl_endpoint">API エンドポイント URL</label></th>
						<td>
							<input name="<?php echo esc_attr( APL_OPT_ENDPOINT ); ?>" id="apl_endpoint"
								type="url" class="regular-text" value="<?php echo $endpoint; ?>"
								placeholder="https://xxxx.execute-api.ap-northeast-1.amazonaws.com/prod" />
							<p class="description">CloudFormation Outputs の ApiEndpoint。末尾の <code>/suggest</code> は付けないでください（自動付与）。</p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="apl_secret">共有シークレット (X-Api-Secret)</label></th>
						<td>
							<input name="<?php echo esc_attr( APL_OPT_SHARED_SECRET ); ?>" id="apl_secret"
								type="password" class="regular-text" value="<?php echo $secret; ?>" autocomplete="off" />
							<p class="description">デプロイ時に指定した SharedSecret と同じ値。</p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="apl_api_key">API キー (x-api-key)</label></th>
						<td>
							<input name="<?php echo esc_attr( APL_OPT_API_KEY ); ?>" id="apl_api_key"
								type="password" class="regular-text" value="<?php echo $api_key; ?>" autocomplete="off" />
							<p class="description">API Gateway の Usage Plan に紐づく APIキー値（<code>aws apigateway get-api-keys --include-values</code> で取得）。</p>
						</td>
					</tr>
				</table>
				<?php submit_button(); ?>
			</form>
		</div>
		<?php
	}
}
