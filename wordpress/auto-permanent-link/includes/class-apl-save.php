<?php
/**
 * サーバー側 slug 確定。
 *
 * フロントで #post_name / #new-post-slug に書いてもコアの JS が保存前に上書き（空リセット）する
 * ため、フロントの競合を根絶する唯一確実な方法として「保存時にサーバーで slug を強制」する。
 *
 * 仕組み:
 *  - メタボックスの隠しフィールド apl_selected_slug に、ユーザーが「適用」で選んだ slug が入る。
 *  - 投稿保存時 wp_insert_post_data フックで、権限 + nonce を検証し、値があれば post_name を強制。
 *  - sanitize_title で WP 標準の slug 正規化を通す（多言語・重複はコアに委譲）。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class APL_Save {

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		// data フィルタで post_name を確定（保存直前、DB 書き込み前）。
		add_filter( 'wp_insert_post_data', array( $this, 'force_slug' ), 10, 2 );
	}

	/**
	 * @param array $data    これから保存される投稿カラム（post_name 含む）。
	 * @param array $postarr 送信された生データ（$_POST 相当）。
	 */
	public function force_slug( $data, $postarr ) {
		// リビジョン/オートセーブは触らない。
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
			return $data;
		}
		if ( isset( $data['post_type'] ) && 'revision' === $data['post_type'] ) {
			return $data;
		}

		// 選択 slug が来ていなければ何もしない（通常の保存を尊重）。
		if ( empty( $postarr['apl_selected_slug'] ) ) {
			return $data;
		}

		// nonce 検証。
		$nonce = isset( $postarr['apl_slug_nonce'] ) ? $postarr['apl_slug_nonce'] : '';
		if ( ! wp_verify_nonce( $nonce, 'apl_save_slug' ) ) {
			return $data;
		}

		// 権限: 表示/実行と同じ境界（管理者・編集者）。
		$post_id = isset( $postarr['ID'] ) ? absint( $postarr['ID'] ) : 0;
		if ( ! current_user_can( 'edit_others_posts' ) ) {
			return $data;
		}

		// WP 標準の slug 正規化を通す（英語想定だが多言語・記号も安全に処理）。
		$slug = sanitize_title( wp_unslash( $postarr['apl_selected_slug'] ) );
		if ( '' === $slug ) {
			return $data;
		}

		$data['post_name'] = $slug;
		return $data;
	}
}
