<?php
/**
 * 投稿編集画面のメタボックス「パーマリンク推奨」。
 * ボタン + 候補表示領域を描画し、JS/CSS を enqueue、nonce と REST パスを JS に渡す。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class APL_Metabox {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'add_meta_boxes', array( $this, 'add_metabox' ) );
		add_action( 'admin_enqueue_scripts', array( $this, 'enqueue' ) );
	}

	public function add_metabox() {
		// 管理者・編集者のみに表示（寄稿者・投稿者には出さない）。
		// edit_others_posts は Administrator/Editor が持ち、Author/Contributor は持たない権限。
		if ( ! current_user_can( 'edit_others_posts' ) ) {
			return;
		}
		// 投稿タイプ post に対して side カラムへ追加（必要なら他タイプも追加可能）。
		add_meta_box(
			'apl_permalink_suggest',
			'パーマリンク推奨',
			array( $this, 'render' ),
			'post',
			'side',
			'high'
		);
	}

	public function render( $post ) {
		?>
		<div class="apl-box">
			<p class="apl-desc">記事タイトルから英語スラッグ候補を AI が提案します。</p>
			<button type="button" class="button button-primary apl-generate" id="apl-generate">
				候補を生成
			</button>
			<label class="apl-excerpt-toggle">
				<input type="checkbox" id="apl-use-excerpt" checked /> 本文冒頭も考慮する
			</label>
			<div class="apl-status" id="apl-status" aria-live="polite"></div>
			<ul class="apl-suggestions" id="apl-suggestions"></ul>
			<?php wp_nonce_field( 'apl_save_slug', 'apl_slug_nonce' ); ?>
			<input type="hidden" id="apl_selected_slug" name="apl_selected_slug" value="" />
		</div>
		<?php
	}

	public function enqueue( $hook ) {
		if ( 'post.php' !== $hook && 'post-new.php' !== $hook ) {
			return;
		}
		// 表示条件と揃える: 管理者・編集者以外には asset を配らない。
		if ( ! current_user_can( 'edit_others_posts' ) ) {
			return;
		}
		wp_enqueue_style(
			'apl-admin',
			APL_PLUGIN_URL . 'assets/css/admin.css',
			array(),
			APL_VERSION
		);
		wp_enqueue_script(
			'apl-admin',
			APL_PLUGIN_URL . 'assets/js/admin.js',
			array(),
			APL_VERSION,
			true
		);
		wp_localize_script(
			'apl-admin',
			'APL_CONFIG',
			array(
				'restUrl' => esc_url_raw( rest_url( 'auto-permanent-link/v1/suggest' ) ),
				'nonce'   => wp_create_nonce( 'wp_rest' ),
			)
		);
	}
}
